import json
import subprocess
import tempfile
from pathlib import Path


class AudioDecodeError(Exception):
    """Input audio could not be decoded."""


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise AudioDecodeError(proc.stderr.decode(errors="replace")[-500:])
    return proc


def normalize_to_wav(data: bytes) -> bytes:
    """Any browser/iMessage recording (webm/m4a/wav) -> WAV 48kHz mono.

    48kHz, NOT 16kHz: STS reconstructs phonemes from spectral detail above 8kHz
    (consonants) — 16k input made it hallucinate words (verified A/B on real takes).
    Whisper-based engines resample internally, so full band costs them nothing.

    NO filtering (highpass/loudnorm/silence-trim) — A/B-tested worse than plain:
    ElevenLabs handles level/noise internally and our conditioning interfered
    with its phoneme tracking (transcript WER degraded on real takes).

    Uses temp files, not pipes: mp4/m4a needs seekable input (moov atom).
    """
    with tempfile.NamedTemporaryFile(suffix=".bin") as src, tempfile.NamedTemporaryFile(
        suffix=".wav"
    ) as dst:
        src.write(data)
        src.flush()
        _run(["ffmpeg", "-y", "-i", src.name, "-ar", "48000", "-ac", "1", "-f", "wav", dst.name])
        return Path(dst.name).read_bytes()


def duration_seconds(wav: bytes) -> float:
    with tempfile.NamedTemporaryFile(suffix=".wav") as f:
        f.write(wav)
        f.flush()
        proc = _run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", f.name]
        )
        # fully-trimmed (silent) takes may have no duration field — treat as 0s
        return float(json.loads(proc.stdout).get("format", {}).get("duration", 0.0))


def wav_to_mp3(wav: bytes) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".wav") as src, tempfile.NamedTemporaryFile(
        suffix=".mp3"
    ) as dst:
        src.write(wav)
        src.flush()
        _run(["ffmpeg", "-y", "-i", src.name, "-b:a", "128k", dst.name])
        return Path(dst.name).read_bytes()


def placeholder_mp3(seconds: float = 1.0) -> bytes:
    """Synthesized tone MP3 — used by the stub engine for text-only input."""
    with tempfile.NamedTemporaryFile(suffix=".mp3") as dst:
        _run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                "-b:a", "64k", dst.name,
            ]
        )
        return Path(dst.name).read_bytes()
