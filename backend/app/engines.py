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
ELEVENLABS_MODEL = "eleven_multilingual_sts_v2"


class ElevenLabsEngine:
    """Path A: genuine speech-to-speech. voice_id here is the ELEVENLABS voice id."""

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client or httpx.AsyncClient(timeout=60.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def transform(self, wav: bytes | None, voice_id: str, text: str | None) -> bytes:
        resp = await self._client.post(
            ELEVENLABS_STS_URL.format(voice_id=voice_id),
            headers={"xi-api-key": os.environ.get("ELEVENLABS_API_KEY", "")},
            files={"audio": ("input.wav", wav, "audio/wav")},
            data={"model_id": ELEVENLABS_MODEL},
        )
        if resp.status_code != 200:
            # body stays server-side: EngineError messages flow into client-facing 502s
            logger.warning("ElevenLabs STS %s: %s", resp.status_code, resp.text[:300])
            raise EngineError(f"ElevenLabs returned {resp.status_code}")
        return resp.content


class StubModalEngine:
    """Path B placeholder. John: replace this class with the Whisper+TTS Modal client —
    same signature, nothing else in the app changes."""

    async def transform(self, wav: bytes | None, voice_id: str, text: str | None) -> bytes:
        # voice_id intentionally unused — stub returns passthrough/placeholder audio
        if wav is not None:
            return await asyncio.to_thread(audio.wav_to_mp3, wav)
        return await asyncio.to_thread(audio.placeholder_mp3)
