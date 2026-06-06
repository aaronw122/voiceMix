import os
import uuid
from pathlib import Path


def audio_dir() -> Path:
    d = Path(os.environ.get("AUDIO_DIR", "data/audio"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def save(data: bytes) -> str:
    """Persist MP3 bytes; return the durable object key (no extension, no URL)."""
    key = uuid.uuid4().hex
    (audio_dir() / f"{key}.mp3").write_bytes(data)
    return key


def url_for(key: str) -> str:
    if "/" in key or "\\" in key or ".." in key:
        raise ValueError(f"Invalid storage key: {key!r}")
    base = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
    return f"{base}/audio/{key}.mp3"
