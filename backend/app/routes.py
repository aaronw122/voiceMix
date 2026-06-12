import asyncio
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from . import db, storage
from .audio import AudioDecodeError, duration_seconds, normalize_to_wav
from .engines import EngineError
from .voices import get_voice, list_voices

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

MAX_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_SECONDS = 60.0


def _base_url(request: Request) -> str:
    # explicit BASE_URL wins (prod sets the public Cloudflare origin); otherwise
    # derive from the request so any host/port works without configuration —
    # the hardcoded localhost default produced dead links three separate times
    return (os.environ.get("BASE_URL") or str(request.base_url)).rstrip("/")


async def _read_and_normalize(upload: UploadFile) -> bytes:
    data = await upload.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Recording is over the 10 MB limit")
    try:
        wav = await asyncio.to_thread(normalize_to_wav, data)
    except AudioDecodeError:
        raise HTTPException(422, "Couldn't read that recording")
    if await asyncio.to_thread(duration_seconds, wav) > MAX_SECONDS:
        raise HTTPException(422, "Recording is over the 1 minute limit")
    if os.environ.get("DEBUG_SAVE_INPUTS") == "1":  # bisect aid: inspect exactly what engines receive
        debug_dir = Path(os.environ.get("AUDIO_DIR", "data/audio")).parent / "debug-inputs"
        debug_dir.mkdir(parents=True, exist_ok=True)
        stem = uuid.uuid4().hex[:8]
        (debug_dir / f"{stem}.raw.bin").write_bytes(data)  # exactly what the browser uploaded
        (debug_dir / f"{stem}.wav").write_bytes(wav)  # after ffmpeg normalize
    return wav


def _persist(mp3: bytes, voice_name: str, request: Request) -> dict:
    key = storage.save(mp3)
    clip_id = uuid.uuid4().hex[:10]
    title = f"{voice_name} — voiceMix clip"
    db.insert_clip(clip_id, title, key)
    base = _base_url(request)
    return {
        "url": f"{base}/share/{clip_id}",
        "title": title,
        "audioUrl": storage.url_for(key, base),
    }


@router.get("/voices")
async def voices():
    return list_voices()


@router.post("/impersonate")
async def impersonate(
    request: Request,
    voiceId: str = Form(...),
    audio: UploadFile | None = File(None),
    text: str | None = Form(None),
):
    text = text or None  # browser forms send empty fields as "" — treat as absent
    voice = get_voice(voiceId)
    if voice is None:
        raise HTTPException(404, f"Unknown voice: {voiceId}")
    if voice["engine"] != "modal":
        raise HTTPException(422, f"Voice {voiceId} belongs on POST /convert")
    if (audio is None) == (text is None):
        raise HTTPException(422, "Send exactly one of: audio, text")

    wav = await _read_and_normalize(audio) if audio is not None else None
    # per-voice migration: "tts" voices hit the fine-tuned GPT-SoVITS endpoint, the rest
    # stay on RVC. Both live behind /impersonate so the frontend contract is unchanged.
    engine_key = "tts_modal" if voice.get("modalEngine") == "tts" else "modal"
    engine = request.app.state.engines[engine_key]
    try:
        mp3 = await engine.transform(wav, voice["id"], text)
    except EngineError as e:
        raise HTTPException(502, f"Voice engine failed: {e}")

    return _persist(mp3, voice["name"], request)


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

    return _persist(mp3, voice["name"], request)


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@router.get("/share/{clip_id}", response_class=HTMLResponse)
async def share(request: Request, clip_id: str):
    clip = db.get_clip(clip_id)
    if clip is None:
        raise HTTPException(404, "Clip not found")
    base = _base_url(request)
    return templates.TemplateResponse(
        request,
        "share.html",
        {
            "title": clip["title"],
            "audio_url": storage.url_for(clip["object_key"], base),
            "page_url": f"{base}/share/{clip_id}",
            "image_url": f"{base}/static/share-card.png",
        },
    )
