# voiceMix Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the voiceMix backend — `POST /convert` (real ElevenLabs STS), `POST /impersonate` (stubbed behind the same contract), `GET /voices`, `GET /share/:id`, and static audio serving — per the approved spec at `docs/superpowers/specs/2026-06-06-backend-two-endpoints-design.md`.

**Architecture:** Single FastAPI app (factory pattern, `uvicorn --factory`). Upload → ffmpeg-normalize to WAV 16kHz mono → `VoiceEngine.transform()` → MP3 saved to local disk → SQLite row → `{url, title, audioUrl}`. Engines hang off `app.state.engines` so tests swap in fakes and John later swaps the Modal engine without touching routes.

**Tech Stack:** Python 3.12 via `uv`, FastAPI, `python-multipart`, Jinja2, httpx (ElevenLabs calls + tests via `TestClient`), SQLite (stdlib), ffmpeg/ffprobe (subprocess), pytest.

**Conventions for every task:**
- Working directory: `/Users/thegermanaz/p/python/voice-mix/voiceMix/backend` unless stated otherwise.
- Run tests with `uv run pytest <path> -v`.
- All env config: `AUDIO_DIR` (default `data/audio`), `DB_PATH` (default `data/voicemix.db`), `BASE_URL` (default `http://localhost:8000`), `ELEVENLABS_API_KEY` (no default).

---

### Task 0: Toolchain setup (one-time, no code)

**Files:** none

- [ ] **Step 1: Install ffmpeg** (verified missing on this machine; ffprobe ships with it)

```bash
brew install ffmpeg
```

- [ ] **Step 2: Verify**

Run: `ffmpeg -version | head -1 && ffprobe -version | head -1`
Expected: two version lines, no "command not found".

---

### Task 1: Project scaffold + app factory

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/.env.example`
- Create: `backend/app/__init__.py` (empty)
- Create: `backend/app/main.py`
- Create: `backend/tests/__init__.py` (empty)
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_health.py`
- Modify: `.gitignore` (repo root)

- [ ] **Step 1: Write `backend/pyproject.toml`**

```toml
[project]
name = "voicemix-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi",
    "uvicorn[standard]",
    "python-multipart",
    "jinja2",
    "httpx",
]

[dependency-groups]
dev = ["pytest"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Write `backend/.env.example`**

```bash
ELEVENLABS_API_KEY=sk_your_key_here
BASE_URL=http://localhost:8000
# AUDIO_DIR=data/audio
# DB_PATH=data/voicemix.db
```

- [ ] **Step 3: Append to root `.gitignore`**

```gitignore
# backend
backend/data/
backend/.env
__pycache__/
.venv/
*.pyc
```

- [ ] **Step 4: Write the failing test — `backend/tests/test_health.py`**

```python
def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
```

- [ ] **Step 5: Write `backend/tests/conftest.py`**

The fixture sets env vars to a tmp dir BEFORE building the app, so nothing writes into the repo. `FakeEngine` returns known bytes so route tests never hit the network.

```python
import pytest
from fastapi.testclient import TestClient

FAKE_MP3 = b"ID3FAKE_MP3_BYTES"


class FakeEngine:
    """Test double for any VoiceEngine. Records the last call."""

    def __init__(self, output: bytes = FAKE_MP3):
        self.output = output
        self.last_call = None

    async def transform(self, wav, voice_id, text=None):
        self.last_call = {"wav": wav, "voice_id": voice_id, "text": text}
        return self.output


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIO_DIR", str(tmp_path / "audio"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "voicemix.db"))
    monkeypatch.setenv("BASE_URL", "http://testserver")
    from app.main import create_app

    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd backend && uv sync && uv run pytest tests/test_health.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.main'` (or ImportError).

- [ ] **Step 7: Write `backend/app/main.py` (minimal factory)**

```python
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="voiceMix")

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    return app
```

Also create empty `backend/app/__init__.py` and `backend/tests/__init__.py`.

- [ ] **Step 8: Run test to verify it passes**

Run: `uv run pytest tests/test_health.py -v`
Expected: PASS (1 passed).

- [ ] **Step 9: Commit**

```bash
git add backend/ .gitignore
git commit -m "feat(backend): scaffold FastAPI app factory + healthz"
```

---

### Task 2: Voice catalog + GET /voices

**Files:**
- Create: `backend/app/voices.py`
- Create: `backend/app/routes.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_voices.py`

- [ ] **Step 1: Write the failing test — `backend/tests/test_voices.py`**

```python
def test_voices_returns_catalog(client):
    resp = client.get("/voices")
    assert resp.status_code == 200
    voices = resp.json()
    assert len(voices) >= 2
    for v in voices:
        assert set(v.keys()) == {"id", "name", "engine", "acceptsText"}
        assert v["engine"] in ("elevenlabs", "modal")
    # internal ElevenLabs IDs must NOT leak to clients
    assert all("elevenVoiceId" not in v for v in voices)


def test_catalog_has_both_engines(client):
    engines = {v["engine"] for v in client.get("/voices").json()}
    assert engines == {"elevenlabs", "modal"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_voices.py -v`
Expected: FAIL — 404 on `/voices`.

- [ ] **Step 3: Write `backend/app/voices.py`**

NOTE: the two `elevenVoiceId` values below are ElevenLabs' well-known premade voices (Adam, Rachel). The smoke test in Task 10 verifies they exist on the team account; swap them there if not.

```python
VOICES = [
    {
        "id": "old-man",
        "name": "Old Man",
        "engine": "elevenlabs",
        "acceptsText": False,
        "elevenVoiceId": "pNInz6obpgDQGcFmaJgB",
    },
    {
        "id": "young-woman",
        "name": "Young Woman",
        "engine": "elevenlabs",
        "acceptsText": False,
        "elevenVoiceId": "21m00Tcm4TlvDq8ikWAM",
    },
    {
        "id": "jfk",
        "name": "JFK",
        "engine": "modal",
        "acceptsText": True,
        "elevenVoiceId": None,
    },
]

_PUBLIC_FIELDS = ("id", "name", "engine", "acceptsText")


def list_voices() -> list[dict]:
    return [{k: v[k] for k in _PUBLIC_FIELDS} for v in VOICES]


def get_voice(voice_id: str) -> dict | None:
    return next((v for v in VOICES if v["id"] == voice_id), None)
```

- [ ] **Step 4: Write `backend/app/routes.py`**

```python
from fastapi import APIRouter

from .voices import list_voices

router = APIRouter()


@router.get("/voices")
async def voices():
    return list_voices()
```

- [ ] **Step 5: Wire the router in `backend/app/main.py`**

```python
from fastapi import FastAPI

from .routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="voiceMix")
    app.include_router(router)

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    return app
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/voices.py backend/app/routes.py backend/app/main.py backend/tests/test_voices.py
git commit -m "feat(backend): voice catalog + GET /voices"
```

---

### Task 3: Disk storage + /audio static mount

**Files:**
- Create: `backend/app/storage.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_storage.py`

- [ ] **Step 1: Write the failing test — `backend/tests/test_storage.py`**

```python
def test_save_and_url_for(app, monkeypatch):
    from app import storage

    key = storage.save(b"mp3-bytes-here")
    assert key  # uuid hex
    assert storage.url_for(key) == f"http://testserver/audio/{key}.mp3"


def test_saved_audio_served_via_static_mount(client):
    from app import storage

    key = storage.save(b"mp3-bytes-here")
    resp = client.get(f"/audio/{key}.mp3")
    assert resp.status_code == 200
    assert resp.content == b"mp3-bytes-here"
```

NOTE: `test_save_and_url_for` takes the `app` fixture (not `client`) only to get the env vars set; the static-mount test needs `client`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_storage.py -v`
Expected: FAIL — `ImportError: cannot import name 'storage'`.

- [ ] **Step 3: Write `backend/app/storage.py`**

```python
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
    base = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
    return f"{base}/audio/{key}.mp3"
```

- [ ] **Step 4: Mount StaticFiles in `backend/app/main.py`**

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import storage
from .routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="voiceMix")
    app.include_router(router)
    app.mount("/audio", StaticFiles(directory=storage.audio_dir()), name="audio")

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    return app
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/storage.py backend/app/main.py backend/tests/test_storage.py
git commit -m "feat(backend): disk storage + /audio static mount"
```

---

### Task 4: SQLite clips table

**Files:**
- Create: `backend/app/db.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_db.py`

- [ ] **Step 1: Write the failing test — `backend/tests/test_db.py`**

```python
def test_insert_and_get_clip(app):
    from app import db

    db.insert_clip("abc123", "Old Man — voiceMix clip", "deadbeef")
    clip = db.get_clip("abc123")
    assert clip["id"] == "abc123"
    assert clip["title"] == "Old Man — voiceMix clip"
    assert clip["object_key"] == "deadbeef"
    assert clip["content_type"] == "audio/mpeg"
    assert clip["created_at"]  # ISO timestamp


def test_get_missing_clip_returns_none(app):
    from app import db

    assert db.get_clip("nope") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db.py -v`
Expected: FAIL — `ImportError: cannot import name 'db'`.

- [ ] **Step 3: Write `backend/app/db.py`**

```python
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _db_path() -> str:
    path = os.environ.get("DB_PATH", "data/voicemix.db")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return path


def init_db() -> None:
    with sqlite3.connect(_db_path()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS clips (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                object_key TEXT NOT NULL,
                content_type TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def insert_clip(clip_id: str, title: str, object_key: str, content_type: str = "audio/mpeg") -> None:
    with sqlite3.connect(_db_path()) as conn:
        conn.execute(
            "INSERT INTO clips VALUES (?, ?, ?, ?, ?)",
            (clip_id, title, object_key, content_type, datetime.now(timezone.utc).isoformat()),
        )


def get_clip(clip_id: str) -> dict | None:
    with sqlite3.connect(_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
        return dict(row) if row else None
```

- [ ] **Step 4: Call `init_db()` in the factory — `backend/app/main.py`**

Add the import and one line at the top of `create_app()`:

```python
from . import db, storage

def create_app() -> FastAPI:
    app = FastAPI(title="voiceMix")
    db.init_db()
    ...
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/db.py backend/app/main.py backend/tests/test_db.py
git commit -m "feat(backend): SQLite clips table"
```

---

### Task 5: ffmpeg audio processing

**Files:**
- Create: `backend/app/audio.py`
- Test: `backend/tests/test_audio.py`

**Design note:** ffmpeg reads from a temp FILE, never stdin — m4a/mp4 containers need seekable input (the `moov` atom is often at the end; piping fails with "moov atom not found"). iMessage sends m4a, so this matters.

- [ ] **Step 1: Write the failing test — `backend/tests/test_audio.py`**

The WAV fixture is generated with the stdlib `wave` module — no network, no binary fixtures in git.

```python
import io
import wave

import pytest


def make_wav(seconds: float = 0.5, rate: int = 8000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return buf.getvalue()


def test_normalize_produces_16k_mono_wav():
    from app.audio import normalize_to_wav

    out = normalize_to_wav(make_wav())
    with wave.open(io.BytesIO(out), "rb") as w:
        assert w.getframerate() == 16000
        assert w.getnchannels() == 1


def test_normalize_rejects_garbage():
    from app.audio import AudioDecodeError, normalize_to_wav

    with pytest.raises(AudioDecodeError):
        normalize_to_wav(b"this is not audio at all")


def test_duration_seconds():
    from app.audio import duration_seconds, normalize_to_wav

    wav = normalize_to_wav(make_wav(seconds=2.0))
    assert duration_seconds(wav) == pytest.approx(2.0, abs=0.2)


def test_wav_to_mp3_roundtrip():
    from app.audio import normalize_to_wav, wav_to_mp3

    mp3 = wav_to_mp3(normalize_to_wav(make_wav()))
    assert len(mp3) > 0
    assert mp3 != b""


def test_placeholder_mp3():
    from app.audio import placeholder_mp3

    assert len(placeholder_mp3()) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_audio.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.audio'`.

- [ ] **Step 3: Write `backend/app/audio.py`**

```python
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
    """Any browser/iMessage recording (webm/m4a/wav) -> WAV 16kHz mono.

    Uses temp files, not pipes: mp4/m4a needs seekable input (moov atom).
    """
    with tempfile.NamedTemporaryFile(suffix=".bin") as src, tempfile.NamedTemporaryFile(
        suffix=".wav"
    ) as dst:
        src.write(data)
        src.flush()
        _run(["ffmpeg", "-y", "-i", src.name, "-ar", "16000", "-ac", "1", "-f", "wav", dst.name])
        return Path(dst.name).read_bytes()


def duration_seconds(wav: bytes) -> float:
    with tempfile.NamedTemporaryFile(suffix=".wav") as f:
        f.write(wav)
        f.flush()
        proc = _run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", f.name]
        )
        return float(json.loads(proc.stdout)["format"]["duration"])


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_audio.py -v`
Expected: all 5 PASS. (If `wav_to_mp3` fails with "Unknown encoder", the brew ffmpeg lacks libmp3lame — `brew reinstall ffmpeg` — but the default bottle includes it.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/audio.py backend/tests/test_audio.py
git commit -m "feat(backend): ffmpeg normalize/duration/mp3 helpers"
```

---

### Task 6: Voice engines (Protocol, ElevenLabs, stub)

**Files:**
- Create: `backend/app/engines.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_engines.py`

- [ ] **Step 1: Write the failing test — `backend/tests/test_engines.py`**

`ElevenLabsEngine` takes an injected `httpx.AsyncClient`, so tests use `httpx.MockTransport` — no network, no key. Engine methods are async; sync tests drive them with `asyncio.run`.

```python
import asyncio

import httpx
import pytest


def test_elevenlabs_engine_posts_sts_and_returns_mp3(monkeypatch):
    from app.engines import ElevenLabsEngine

    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["api_key"] = request.headers.get("xi-api-key")
        return httpx.Response(200, content=b"MP3_FROM_ELEVENLABS")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    engine = ElevenLabsEngine(client=client)
    out = asyncio.run(engine.transform(b"WAVBYTES", "pNInz6obpgDQGcFmaJgB", None))

    assert out == b"MP3_FROM_ELEVENLABS"
    assert "speech-to-speech/pNInz6obpgDQGcFmaJgB" in seen["url"]
    assert seen["api_key"] == "test-key"


def test_elevenlabs_engine_raises_on_api_error(monkeypatch):
    from app.engines import ElevenLabsEngine, EngineError

    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(401, text="bad key"))
    )
    engine = ElevenLabsEngine(client=client)
    with pytest.raises(EngineError):
        asyncio.run(engine.transform(b"WAVBYTES", "voice", None))


def test_stub_modal_engine_transcodes_audio():
    import io
    import wave

    from app.engines import StubModalEngine

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 8000)

    out = asyncio.run(StubModalEngine().transform(buf.getvalue(), "jfk", None))
    assert len(out) > 0


def test_stub_modal_engine_handles_text_only():
    from app.engines import StubModalEngine

    out = asyncio.run(StubModalEngine().transform(None, "jfk", "ask not"))
    assert len(out) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_engines.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.engines'`.

- [ ] **Step 3: Write `backend/app/engines.py`**

```python
import os
from typing import Protocol

import httpx

from . import audio


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

    async def transform(self, wav: bytes | None, voice_id: str, text: str | None) -> bytes:
        resp = await self._client.post(
            ELEVENLABS_STS_URL.format(voice_id=voice_id),
            headers={"xi-api-key": os.environ.get("ELEVENLABS_API_KEY", "")},
            files={"audio": ("input.wav", wav, "audio/wav")},
            data={"model_id": ELEVENLABS_MODEL},
        )
        if resp.status_code != 200:
            raise EngineError(f"ElevenLabs returned {resp.status_code}: {resp.text[:300]}")
        return resp.content


class StubModalEngine:
    """Path B placeholder. John: replace this class with the Whisper+TTS Modal client —
    same signature, nothing else in the app changes."""

    async def transform(self, wav: bytes | None, voice_id: str, text: str | None) -> bytes:
        if wav is not None:
            return audio.wav_to_mp3(wav)
        return audio.placeholder_mp3()
```

- [ ] **Step 4: Register engines in the factory — `backend/app/main.py`**

Add after `db.init_db()`:

```python
from .engines import ElevenLabsEngine, StubModalEngine

    app.state.engines = {
        "elevenlabs": ElevenLabsEngine(),
        "modal": StubModalEngine(),
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/engines.py backend/app/main.py backend/tests/test_engines.py
git commit -m "feat(backend): VoiceEngine protocol, ElevenLabs STS engine, modal stub"
```

---

### Task 7: POST /convert — happy path

**Files:**
- Modify: `backend/app/routes.py`
- Modify: `backend/app/main.py` (error-shape handler)
- Test: `backend/tests/test_convert.py`

- [ ] **Step 1: Write the failing test — `backend/tests/test_convert.py`**

```python
import io
import wave

from tests.conftest import FAKE_MP3, FakeEngine


def make_wav(seconds: float = 0.5) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * int(8000 * seconds))
    return buf.getvalue()


def post_convert(client, voice_id="old-man", audio_bytes=None):
    return client.post(
        "/convert",
        files={"audio": ("rec.wav", audio_bytes or make_wav(), "audio/wav")},
        data={"voiceId": voice_id},
    )


def test_convert_happy_path(client, app):
    fake = FakeEngine()
    app.state.engines["elevenlabs"] = fake

    resp = post_convert(client)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"url", "title", "audioUrl"}
    assert body["title"] == "Old Man — voiceMix clip"
    assert "/share/" in body["url"]

    # the engine got the ELEVENLABS id, not the catalog id
    assert fake.last_call["voice_id"] == "pNInz6obpgDQGcFmaJgB"

    # the audioUrl actually serves the engine's MP3
    audio_resp = client.get(body["audioUrl"].replace("http://testserver", ""))
    assert audio_resp.status_code == 200
    assert audio_resp.content == FAKE_MP3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_convert.py -v`
Expected: FAIL — 404 (`/convert` doesn't exist).

- [ ] **Step 3: Implement `/convert` in `backend/app/routes.py`** (full file)

```python
import os
import uuid

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from . import db, storage
from .audio import AudioDecodeError, duration_seconds, normalize_to_wav
from .engines import EngineError
from .voices import get_voice, list_voices

router = APIRouter()

MAX_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_SECONDS = 60.0


def _base_url() -> str:
    return os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")


async def _read_and_normalize(upload: UploadFile) -> bytes:
    data = await upload.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Recording is over the 10 MB limit")
    try:
        wav = normalize_to_wav(data)
    except AudioDecodeError:
        raise HTTPException(422, "Couldn't read that recording")
    if duration_seconds(wav) > MAX_SECONDS:
        raise HTTPException(422, "Recording is over the 1 minute limit")
    return wav


def _persist(mp3: bytes, voice_name: str) -> dict:
    key = storage.save(mp3)
    clip_id = uuid.uuid4().hex[:10]
    title = f"{voice_name} — voiceMix clip"
    db.insert_clip(clip_id, title, key)
    return {
        "url": f"{_base_url()}/share/{clip_id}",
        "title": title,
        "audioUrl": storage.url_for(key),
    }


@router.get("/voices")
async def voices():
    return list_voices()


@router.post("/convert")
async def convert(
    request: Request,
    audio: UploadFile = File(...),
    voiceId: str = Form(...),
):
    voice = get_voice(voiceId)
    if voice is None:
        raise HTTPException(404, f"Unknown voice: {voiceId}")
    if voice["engine"] != "elevenlabs":
        raise HTTPException(422, f"Voice {voiceId} belongs on POST /impersonate")

    wav = await _read_and_normalize(audio)
    engine = request.app.state.engines["elevenlabs"]
    try:
        mp3 = await engine.transform(wav, voice["elevenVoiceId"], None)
    except EngineError as e:
        raise HTTPException(502, f"Voice engine failed: {e}")

    return _persist(mp3, voice["name"])
```

- [ ] **Step 4: Add the `{"error": ...}` response shape — `backend/app/main.py`**

Per spec, all errors return `{"error": "<message>"}`. Add to `create_app()`:

```python
from fastapi import HTTPException
from fastapi.responses import JSONResponse

    @app.exception_handler(HTTPException)
    async def error_shape(request, exc: HTTPException):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes.py backend/app/main.py backend/tests/test_convert.py
git commit -m "feat(backend): POST /convert happy path with engine seam"
```

---

### Task 8: POST /convert — validation & errors

**Files:**
- Modify: `backend/tests/test_convert.py` (append tests; implementation already exists from Task 7 — these tests pin the behavior)

- [ ] **Step 1: Append the validation tests to `backend/tests/test_convert.py`**

```python
def test_unknown_voice_404(client):
    resp = post_convert(client, voice_id="not-a-voice")
    assert resp.status_code == 404
    assert "error" in resp.json()


def test_modal_voice_on_convert_422(client):
    resp = post_convert(client, voice_id="jfk")
    assert resp.status_code == 422
    assert "impersonate" in resp.json()["error"]


def test_oversize_upload_413(client):
    resp = post_convert(client, audio_bytes=b"\x00" * (10 * 1024 * 1024 + 1))
    assert resp.status_code == 413


def test_garbage_audio_422(client):
    resp = post_convert(client, audio_bytes=b"definitely not audio")
    assert resp.status_code == 422
    assert resp.json()["error"] == "Couldn't read that recording"


def test_too_long_recording_422(client):
    resp = post_convert(client, audio_bytes=make_wav(seconds=61))
    assert resp.status_code == 422
    assert "1 minute" in resp.json()["error"]


def test_engine_failure_502(client, app):
    from app.engines import EngineError

    class ExplodingEngine:
        async def transform(self, wav, voice_id, text=None):
            raise EngineError("upstream sad")

    app.state.engines["elevenlabs"] = ExplodingEngine()
    resp = post_convert(client)
    assert resp.status_code == 502
    assert "error" in resp.json()
```

- [ ] **Step 2: Run tests — most should already pass (Task 7 implemented the checks)**

Run: `uv run pytest tests/test_convert.py -v`
Expected: all PASS. If any fail, fix `routes.py` to match the test, not vice versa — the tests encode the spec's error table.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_convert.py
git commit -m "test(backend): pin /convert validation + error contract"
```

---

### Task 9: POST /impersonate (stubbed engine, full contract)

**Files:**
- Modify: `backend/app/routes.py`
- Test: `backend/tests/test_impersonate.py`

- [ ] **Step 1: Write the failing test — `backend/tests/test_impersonate.py`**

```python
from tests.conftest import FAKE_MP3, FakeEngine
from tests.test_convert import make_wav


def test_impersonate_with_audio(client, app):
    fake = FakeEngine()
    app.state.engines["modal"] = fake

    resp = client.post(
        "/impersonate",
        files={"audio": ("rec.wav", make_wav(), "audio/wav")},
        data={"voiceId": "jfk"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"url", "title", "audioUrl"}
    assert body["title"] == "JFK — voiceMix clip"
    assert fake.last_call["wav"] is not None
    assert fake.last_call["text"] is None


def test_impersonate_with_text(client, app):
    fake = FakeEngine()
    app.state.engines["modal"] = fake

    resp = client.post("/impersonate", data={"voiceId": "jfk", "text": "ask not"})
    assert resp.status_code == 200
    assert fake.last_call == {"wav": None, "voice_id": "jfk", "text": "ask not"}


def test_impersonate_requires_exactly_one_input(client):
    # neither
    resp = client.post("/impersonate", data={"voiceId": "jfk"})
    assert resp.status_code == 422
    # both
    resp = client.post(
        "/impersonate",
        files={"audio": ("rec.wav", make_wav(), "audio/wav")},
        data={"voiceId": "jfk", "text": "ask not"},
    )
    assert resp.status_code == 422


def test_elevenlabs_voice_on_impersonate_422(client):
    resp = client.post("/impersonate", data={"voiceId": "old-man", "text": "hi"})
    assert resp.status_code == 422


def test_impersonate_unknown_voice_404(client):
    resp = client.post("/impersonate", data={"voiceId": "elvis", "text": "hi"})
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_impersonate.py -v`
Expected: FAIL — 404 (`/impersonate` doesn't exist).

- [ ] **Step 3: Add `/impersonate` to `backend/app/routes.py`**

Append below `convert`:

```python
@router.post("/impersonate")
async def impersonate(
    request: Request,
    voiceId: str = Form(...),
    audio: UploadFile | None = File(None),
    text: str | None = Form(None),
):
    voice = get_voice(voiceId)
    if voice is None:
        raise HTTPException(404, f"Unknown voice: {voiceId}")
    if voice["engine"] != "modal":
        raise HTTPException(422, f"Voice {voiceId} belongs on POST /convert")
    if (audio is None) == (text is None):
        raise HTTPException(422, "Send exactly one of: audio, text")

    wav = await _read_and_normalize(audio) if audio is not None else None
    engine = request.app.state.engines["modal"]
    try:
        mp3 = await engine.transform(wav, voice["id"], text)
    except EngineError as e:
        raise HTTPException(502, f"Voice engine failed: {e}")

    return _persist(mp3, voice["name"])
```

NOTE: the modal engine receives the CATALOG id (`voice["id"]`) — John's engine maps it to his model/reference audio. ElevenLabs gets `voice["elevenVoiceId"]`. This asymmetry is intentional.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes.py backend/tests/test_impersonate.py
git commit -m "feat(backend): POST /impersonate behind stub engine"
```

---

### Task 10: GET /share/:id (server-rendered HTML)

**Files:**
- Create: `backend/app/templates/share.html`
- Modify: `backend/app/routes.py`
- Test: `backend/tests/test_share.py`

- [ ] **Step 1: Write the failing test — `backend/tests/test_share.py`**

```python
def test_share_page_renders(client, app):
    from app import db, storage

    key = storage.save(b"mp3")
    db.insert_clip("clip12345", "Old Man — voiceMix clip", key)

    resp = client.get("/share/clip12345")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    html = resp.text
    assert "Old Man — voiceMix clip" in html
    assert f"/audio/{key}.mp3" in html
    assert "<audio" in html
    assert 'property="og:title"' in html


def test_share_unknown_id_404(client):
    resp = client.get("/share/nope")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_share.py -v`
Expected: FAIL — 404 with JSON body on the first test (route missing).

- [ ] **Step 3: Write `backend/app/templates/share.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{{ title }}</title>
  <meta property="og:title" content="{{ title }}" />
  <meta property="og:type" content="music.song" />
  <meta property="og:audio" content="{{ audio_url }}" />
  <style>
    body { font-family: -apple-system, sans-serif; display: grid; place-items: center;
           min-height: 100vh; margin: 0; background: #111; color: #eee; }
    main { text-align: center; padding: 2rem; }
    audio { margin-top: 1.5rem; width: min(90vw, 24rem); }
  </style>
</head>
<body>
  <main>
    <h1>{{ title }}</h1>
    <audio controls src="{{ audio_url }}"></audio>
  </main>
</body>
</html>
```

- [ ] **Step 4: Add the route to `backend/app/routes.py`**

Add imports and the route:

```python
from pathlib import Path

from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@router.get("/share/{clip_id}", response_class=HTMLResponse)
async def share(request: Request, clip_id: str):
    clip = db.get_clip(clip_id)
    if clip is None:
        raise HTTPException(404, "Clip not found")
    return templates.TemplateResponse(
        request,
        "share.html",
        {"title": clip["title"], "audio_url": storage.url_for(clip["object_key"])},
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/templates/share.html backend/app/routes.py backend/tests/test_share.py
git commit -m "feat(backend): server-rendered /share/:id page with OG tags"
```

---

### Task 11: Smoke script + README

**Files:**
- Create: `backend/scripts/smoke.py`
- Create: `backend/README.md`

- [ ] **Step 1: Write `backend/scripts/smoke.py`** (manual, real key — NOT run in CI/tests)

```python
"""Manual smoke test: one real round-trip through ElevenLabs STS.

Usage:
    cd backend
    ELEVENLABS_API_KEY=sk_... uv run python scripts/smoke.py

Verifies: the API key works, the catalog's elevenVoiceId values exist on this
account, and STS returns playable MP3 bytes.
"""

import asyncio
import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.audio import placeholder_mp3, normalize_to_wav  # noqa: E402
from app.engines import ElevenLabsEngine  # noqa: E402
from app.voices import VOICES  # noqa: E402


async def main() -> None:
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        sys.exit("Set ELEVENLABS_API_KEY first")

    # 1. List account voices; check our catalog ids exist
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            "https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": key}
        )
        resp.raise_for_status()
        account_ids = {v["voice_id"] for v in resp.json()["voices"]}
    for v in VOICES:
        if v["engine"] == "elevenlabs":
            status = "OK" if v["elevenVoiceId"] in account_ids else "MISSING — fix voices.py"
            print(f"  {v['id']:<14} {v['elevenVoiceId']}: {status}")

    # 2. One real STS round-trip with a synthesized input clip
    wav = normalize_to_wav(placeholder_mp3(seconds=2.0))
    engine = ElevenLabsEngine()
    voice = next(v for v in VOICES if v["engine"] == "elevenlabs")
    mp3 = await engine.transform(wav, voice["elevenVoiceId"], None)
    out = "smoke_output.mp3"
    with open(out, "wb") as f:
        f.write(mp3)
    print(f"STS round-trip OK -> {out} ({len(mp3)} bytes). Play it to confirm.")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Write `backend/README.md`**

```markdown
# voiceMix backend

FastAPI service: `/convert` (ElevenLabs STS), `/impersonate` (stub → John's Modal engine),
`/voices`, `/share/:id`, static `/audio/*`. Spec: `../docs/superpowers/specs/2026-06-06-backend-two-endpoints-design.md`.

## Run

    brew install ffmpeg          # once
    cd backend
    uv sync
    cp .env.example .env         # add the real ELEVENLABS_API_KEY
    set -a; source .env; set +a
    uv run uvicorn --factory app.main:create_app --reload

## Test

    uv run pytest                          # no network, no key needed
    uv run python scripts/smoke.py         # manual: real ElevenLabs round-trip

## John: plugging in the Modal engine

Replace `StubModalEngine` in `app/engines.py` with a class implementing:

    async def transform(self, wav: bytes | None, voice_id: str, text: str | None) -> bytes

`voice_id` is the catalog id from `app/voices.py` (e.g. "jfk"); exactly one of
`wav`/`text` is non-None; return MP3 bytes. Raise `EngineError` on failure → the
route returns a clean 502. Nothing else needs to change.
```

- [ ] **Step 3: Sanity-run the full suite + boot the server once**

```bash
uv run pytest -v
uv run uvicorn --factory app.main:create_app --port 8000 &
sleep 2 && curl -s http://localhost:8000/voices && curl -s http://localhost:8000/healthz
kill %1
```

Expected: all tests pass; both curls return JSON.

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/smoke.py backend/README.md
git commit -m "feat(backend): smoke script + README with engine handoff notes"
```

---

## Done criteria (maps to spec)

- [ ] All routes from the spec table exist and return the contract shapes.
- [ ] Full test suite green with zero network access and no API key.
- [ ] Error table from the spec covered by tests (404/413/422/502, `{"error": ...}` body).
- [ ] `smoke.py` run once with the real key → playable MP3 (blocked on the API-key TODO in plan.md).
- [ ] John's handoff documented in README; stub replaceable without touching routes.
