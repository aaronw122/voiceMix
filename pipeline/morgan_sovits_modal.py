"""
morgan_sovits_modal.py — Morgan Freeman ASR→TTS demo on Modal.

This is a separate path from the RVC demo:
  input audio -> faster-whisper transcript -> GPT-SoVITS TTS with Morgan reference -> WAV

One-time setup:
  modal volume put --force rvc-vol data/raw/Morgan_Freeman.wav /sovits/morgan_freeman/Morgan_Freeman.wav
  modal run morgan_sovits_modal.py::prepare --offset-seconds 0 --duration-seconds 8

Deploy:
  modal deploy morgan_sovits_modal.py --name voicemix-morgan-sovits

Use:
  curl -X POST --data-binary @input.wav -o output.wav \
    "https://<workspace>--voicemix-morgan-sovits-sovits-api.modal.run/convert?voice=morgan_freeman"
"""
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import modal


VOLUME_NAME = "rvc-vol"
VOICE_ID = "morgan_freeman"
GPT_SOVITS_ROOT = Path("/workspace/GPT-SoVITS")
SOVITS_API_URL = "http://127.0.0.1:9880"
SOVITS_API_LOG = Path("/tmp/gpt_sovits_api.log")
MAX_INPUT_SECONDS = 30.0
MAX_INPUT_BYTES = 25 * 1024 * 1024

VOL_ROOT = Path("/vol") / "sovits" / VOICE_ID
VOL_SOURCE = VOL_ROOT / "Morgan_Freeman.wav"
VOL_REF = VOL_ROOT / "ref.wav"
VOL_PROMPT = VOL_ROOT / "prompt.txt"
VOL_METADATA = VOL_ROOT / "metadata.json"

GPU = os.environ.get("MODAL_SOVITS_GPU", "H100")
MIN_CONTAINERS = int(os.environ.get("MODAL_SOVITS_MIN_CONTAINERS", "0"))
MAX_CONTAINERS = int(os.environ.get("MODAL_SOVITS_MAX_CONTAINERS", "1"))
SCALEDOWN_WINDOW = int(os.environ.get("MODAL_SOVITS_SCALEDOWN_WINDOW", "1200"))


sovits_image = (
    modal.Image.from_registry("xxxxrt666/gpt-sovits:latest-cu128")
    .pip_install("fastapi[standard]", "faster-whisper", "requests")
)
app = modal.App("morgan-sovits")
vol = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)

_sovits_process: subprocess.Popen | None = None


def _run(args: list[str], cwd: Path | None = None, timeout: int | None = None) -> subprocess.CompletedProcess:
    print("$", " ".join(map(str, args)), flush=True)
    return subprocess.run(args, cwd=cwd, timeout=timeout, check=True)


def _duration_seconds(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    return float(result.stdout.strip())


def _ensure_gpt_sovits_layout() -> None:
    """Modal does not run the Docker CMD, so recreate GPT-SoVITS model symlinks."""
    links = [
        (Path("/workspace/models/pretrained_models"), GPT_SOVITS_ROOT / "GPT_SoVITS/pretrained_models"),
        (Path("/workspace/models/G2PWModel"), GPT_SOVITS_ROOT / "GPT_SoVITS/text/G2PWModel"),
        (Path("/workspace/models/asr_models"), GPT_SOVITS_ROOT / "tools/asr/models"),
        (Path("/workspace/models/uvr5_weights"), GPT_SOVITS_ROOT / "tools/uvr5/uvr5_weights"),
    ]
    for src, dst in links:
        if dst.is_symlink():
            continue
        if dst.exists():
            if dst.is_dir() and not any(dst.iterdir()):
                dst.rmdir()
            else:
                continue
        if not src.exists():
            print(f"warning: expected GPT-SoVITS model path missing: {src}", flush=True)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(src, dst)


def _socket_ready(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def _tail_text(path: Path, max_chars: int = 6000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-max_chars:]


def _start_sovits_api() -> None:
    global _sovits_process
    if _sovits_process is not None and _sovits_process.poll() is None and _socket_ready("127.0.0.1", 9880):
        return

    _ensure_gpt_sovits_layout()
    SOVITS_API_LOG.unlink(missing_ok=True)
    log_file = SOVITS_API_LOG.open("ab")
    env = os.environ.copy()
    conda_lib = "/root/conda/lib"
    env["LD_LIBRARY_PATH"] = f"{conda_lib}:{env.get('LD_LIBRARY_PATH', '')}"
    _sovits_process = subprocess.Popen(
        [
            "python",
            "api_v2.py",
            "-a",
            "127.0.0.1",
            "-p",
            "9880",
            "-c",
            "GPT_SoVITS/configs/tts_infer.yaml",
        ],
        cwd=GPT_SOVITS_ROOT,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        env=env,
    )

    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        if _sovits_process.poll() is not None:
            raise RuntimeError(f"GPT-SoVITS API exited during startup:\n{_tail_text(SOVITS_API_LOG)}")
        if _socket_ready("127.0.0.1", 9880):
            return
        time.sleep(1)
    raise TimeoutError(f"GPT-SoVITS API did not start within 180s:\n{_tail_text(SOVITS_API_LOG)}")


def _transcribe(path: Path, model_size: str = "small.en") -> str:
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="cuda", compute_type="float16")
    segments, _ = model.transcribe(
        str(path),
        language="en",
        beam_size=5,
        vad_filter=True,
    )
    text = " ".join(segment.text.strip() for segment in segments).strip()
    if not text:
        raise ValueError(f"no speech transcribed from {path}")
    return text


def _post_sovits_tts(payload: dict) -> bytes:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{SOVITS_API_URL}/tts",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GPT-SoVITS API failed: {detail}") from exc


@app.function(image=sovits_image, gpu=GPU, volumes={"/vol": vol}, timeout=900)
def prepare_morgan_reference(offset_seconds: float = 0.0, duration_seconds: float = 8.0) -> dict:
    if not VOL_SOURCE.exists():
        raise SystemExit(
            f"missing Morgan source at {VOL_SOURCE}; upload it first:\n"
            f"  modal volume put --force {VOLUME_NAME} data/raw/Morgan_Freeman.wav "
            f"/sovits/{VOICE_ID}/Morgan_Freeman.wav"
        )

    VOL_ROOT.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            str(offset_seconds),
            "-t",
            str(duration_seconds),
            "-i",
            str(VOL_SOURCE),
            "-ac",
            "1",
            "-ar",
            "48000",
            "-acodec",
            "pcm_s16le",
            str(VOL_REF),
        ],
        timeout=120,
    )

    prompt_text = _transcribe(VOL_REF)
    VOL_PROMPT.write_text(prompt_text + "\n", encoding="utf-8")
    metadata = {
        "voice": VOICE_ID,
        "source": str(VOL_SOURCE),
        "reference": str(VOL_REF),
        "offset_seconds": offset_seconds,
        "duration_seconds": _duration_seconds(VOL_REF),
        "prompt_text": prompt_text,
        "engine": "faster-whisper+GPT-SoVITS",
    }
    VOL_METADATA.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    vol.commit()
    print(json.dumps(metadata, indent=2), flush=True)
    return metadata


@app.local_entrypoint()
def prepare(offset_seconds: float = 0.0, duration_seconds: float = 8.0) -> None:
    result = prepare_morgan_reference.remote(offset_seconds, duration_seconds)
    print("\nDONE:", result)


@app.function(
    image=sovits_image,
    gpu=GPU,
    volumes={"/vol": vol},
    timeout=900,
    min_containers=MIN_CONTAINERS,
    max_containers=MAX_CONTAINERS,
    scaledown_window=SCALEDOWN_WINDOW,
)
@modal.asgi_app()
def sovits_api():
    from fastapi import FastAPI, HTTPException, Query, Request
    from fastapi.responses import Response

    web_app = FastAPI(title="VoiceMix Morgan Freeman GPT-SoVITS Demo API")

    @web_app.get("/health")
    async def health():
        return {"ok": True, "voice": VOICE_ID, "sovits_started": _socket_ready("127.0.0.1", 9880)}

    @web_app.get("/voices")
    async def voices():
        prompt_text = VOL_PROMPT.read_text(encoding="utf-8").strip() if VOL_PROMPT.exists() else ""
        return {
            "max_input_seconds": MAX_INPUT_SECONDS,
            "output_format": "wav",
            "voices": {
                VOICE_ID: {
                    "label": "Morgan Freeman",
                    "engine": "faster-whisper+GPT-SoVITS",
                    "reference_ready": VOL_REF.exists() and bool(prompt_text),
                    "prompt_text": prompt_text,
                }
            },
        }

    @web_app.post("/convert")
    async def convert(
        request: Request,
        voice: str = Query(VOICE_ID),
        speed: float = Query(1.0, ge=0.5, le=1.5),
    ):
        if voice != VOICE_ID:
            raise HTTPException(status_code=400, detail=f"unknown voice: {voice}")
        if not VOL_REF.exists() or not VOL_PROMPT.exists():
            raise HTTPException(status_code=500, detail="Morgan reference is not prepared")

        body = await request.body()
        if not body:
            raise HTTPException(status_code=400, detail="empty request body")
        if len(body) > MAX_INPUT_BYTES:
            raise HTTPException(status_code=413, detail="input audio is too large")

        request_id = os.urandom(6).hex()
        work_dir = Path("/tmp") / f"morgan_sovits_{request_id}"
        work_dir.mkdir(parents=True, exist_ok=True)
        raw = work_dir / "input"
        wav = work_dir / "input.wav"
        raw.write_bytes(body)

        try:
            _start_sovits_api()
            _run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(raw),
                    "-ac",
                    "1",
                    "-ar",
                    "48000",
                    "-acodec",
                    "pcm_s16le",
                    str(wav),
                ],
                timeout=120,
            )
            duration = _duration_seconds(wav)
            if duration > MAX_INPUT_SECONDS:
                raise HTTPException(
                    status_code=400,
                    detail=f"input audio is {duration:.1f}s; max is {MAX_INPUT_SECONDS:.0f}s",
                )

            text = _transcribe(wav)
            prompt_text = VOL_PROMPT.read_text(encoding="utf-8").strip()
            audio = _post_sovits_tts(
                {
                    "text": text,
                    "text_lang": "en",
                    "ref_audio_path": str(VOL_REF),
                    "prompt_text": prompt_text,
                    "prompt_lang": "en",
                    "media_type": "wav",
                    "text_split_method": "cut5",
                    "batch_size": 1,
                    "speed_factor": speed,
                    "parallel_infer": True,
                    "repetition_penalty": 1.35,
                }
            )
            return Response(
                content=audio,
                media_type="audio/wav",
                headers={
                    "Content-Disposition": f'inline; filename="morgan_freeman_{request_id}.wav"',
                    "X-Voice": VOICE_ID,
                    "X-Transcript": text[:500].replace("\n", " "),
                },
            )
        except HTTPException:
            raise
        except subprocess.CalledProcessError as exc:
            raise HTTPException(status_code=500, detail=f"audio processing failed: {exc}") from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    return web_app
