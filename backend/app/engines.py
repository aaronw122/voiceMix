import asyncio
import logging
import os
from typing import Protocol

import httpx

from . import audio

logger = logging.getLogger(__name__)


class EngineError(Exception):
    """The voice engine failed to produce audio."""


class VoiceEngine(Protocol):
    async def transform(self, wav: bytes | None, voice_id: str, text: str | None) -> bytes:
        """Exactly one of wav/text is provided (routes enforce this). Returns MP3 bytes."""
        ...


ELEVENLABS_STS_URL = "https://api.elevenlabs.io/v1/speech-to-speech/{voice_id}"
# english_sts_v2 locks output to English — multilingual_sts_v2 auto-detects and
# can drift accent/language on short or noisy clips (observed in testing)
ELEVENLABS_MODEL = "eleven_english_sts_v2"


class ElevenLabsEngine:
    """Path A: genuine speech-to-speech. voice_id here is the ELEVENLABS voice id."""

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client or httpx.AsyncClient(timeout=60.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def transform(self, wav: bytes | None, voice_id: str, text: str | None) -> bytes:
        resp = await self._client.post(
            ELEVENLABS_STS_URL.format(voice_id=voice_id),
            params={"output_format": "mp3_44100_192"},  # Creator tier unlocks 192kbps
            headers={"xi-api-key": os.environ.get("ELEVENLABS_API_KEY", "")},
            files={"audio": ("input.wav", wav, "audio/wav")},
            # remove_background_noise: STS needs clean single-speaker input — room noise
            # renders as gibberish (verified via STT round-trip on real recordings).
            # NO voice_settings: A/B-tested worse than API defaults on real takes.
            data={"model_id": ELEVENLABS_MODEL, "remove_background_noise": "true"},
        )
        if resp.status_code != 200:
            # body stays server-side: EngineError messages flow into client-facing 502s
            logger.warning("ElevenLabs STS %s: %s", resp.status_code, resp.text[:300])
            raise EngineError(f"ElevenLabs returned {resp.status_code}")
        return resp.content


ELEVENLABS_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"
ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
ELEVENLABS_STT_MODEL = "scribe_v2"
ELEVENLABS_TTS_MODEL = "eleven_multilingual_v2"


class ElevenLabsSttTtsEngine:
    """Transcribe-then-synthesize: scribe STT -> TTS in the target voice.

    vs STS: output is always cleanly articulated (TTS reads the transcript), but
    the SENDER's delivery/emotion is replaced by the voice's own. Chosen because
    STS warbled on real-world recordings while scribe transcribed them flawlessly.
    Also accepts text directly (skips the STT hop).
    """

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client or httpx.AsyncClient(timeout=60.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _transcribe(self, wav: bytes) -> str:
        resp = await self._client.post(
            ELEVENLABS_STT_URL,
            headers={"xi-api-key": os.environ.get("ELEVENLABS_API_KEY", "")},
            files={"file": ("input.wav", wav, "audio/wav")},
            data={"model_id": ELEVENLABS_STT_MODEL},
        )
        if resp.status_code != 200:
            logger.warning("ElevenLabs STT %s: %s", resp.status_code, resp.text[:300])
            raise EngineError(f"ElevenLabs STT returned {resp.status_code}")
        return (resp.json().get("text") or "").strip()

    async def transform(self, wav: bytes | None, voice_id: str, text: str | None) -> bytes:
        if text is None:
            text = await self._transcribe(wav)
        if not text:
            raise EngineError("couldn't hear any words in that recording")
        resp = await self._client.post(
            ELEVENLABS_TTS_URL.format(voice_id=voice_id),
            params={"output_format": "mp3_44100_192"},
            headers={"xi-api-key": os.environ.get("ELEVENLABS_API_KEY", "")},
            json={"text": text, "model_id": ELEVENLABS_TTS_MODEL},
        )
        if resp.status_code != 200:
            logger.warning("ElevenLabs TTS %s: %s", resp.status_code, resp.text[:300])
            raise EngineError(f"ElevenLabs TTS returned {resp.status_code}")
        return resp.content


class GptSoVitsModalEngine:
    """Our self-hosted fine-tuned GPT-SoVITS v2ProPlus voice on Modal (ASR->TTS).

    Unlike RVC (timbre swap, keeps the sender's delivery), this regenerates the words
    in the target's FULL delivery — accent + cadence — which is the point of the
    migration. Accepts a recording (Modal runs Whisper then TTS) OR text (skips Whisper).
    Contract: POST /synthesize?voice=<id> with a raw WAV body or ?text=; returns MP3.
    """

    def __init__(self, client: httpx.AsyncClient | None = None, base_url: str | None = None):
        self._base = (base_url or os.environ.get("TTS_MODAL_ENDPOINT_URL", "")).rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=120.0)  # cold starts run 20-60s
        self._slots = asyncio.Semaphore(int(os.environ.get("TTS_MODAL_CONCURRENCY", "1")))

    async def aclose(self) -> None:
        await self._client.aclose()

    async def transform(self, wav: bytes | None, voice_id: str, text: str | None) -> bytes:
        async with self._slots:
            try:
                if text is not None:
                    resp = await self._client.post(
                        f"{self._base}/synthesize",
                        params={"voice": voice_id, "text": text},
                    )
                else:
                    resp = await self._client.post(
                        f"{self._base}/synthesize",
                        params={"voice": voice_id},
                        content=wav,
                        headers={"Content-Type": "audio/wav"},
                    )
            except httpx.HTTPError as e:
                logger.warning("GPT-SoVITS modal network error: %r", e)
                raise EngineError("voice engine timed out — try that voice again")
        if resp.status_code != 200:
            logger.warning("GPT-SoVITS modal %s: %s", resp.status_code, resp.text[:300])
            raise EngineError(f"TTS engine returned {resp.status_code}")
        return resp.content  # Modal already returns MP3


class StubModalEngine:
    """Keyless fallback when a modal voice's endpoint URL is unset (passthrough audio)."""

    async def transform(self, wav: bytes | None, voice_id: str, text: str | None) -> bytes:
        # voice_id intentionally unused — stub returns passthrough/placeholder audio
        if wav is not None:
            return await asyncio.to_thread(audio.wav_to_mp3, wav)
        return await asyncio.to_thread(audio.placeholder_mp3)
