"""
serve_rvc_modal.py — deployed RVC inference endpoint for voiceMix.

Stands up the trained {.pth,.index} artifacts on the `rvc-vol` volume behind an
HTTP endpoint, replacing John's `voicemix-rvc-demo` app. Contract matches
backend/app/engines.py::RvcModalEngine exactly:

    POST /convert?voice=<id>&index_rate=<float>&pitch=<int>
    body: raw WAV bytes (Content-Type: audio/wav)
    -> 200 with WAV bytes, or 4xx/5xx {"detail": ...}

Deploy (first run builds the Applio image — ~10-15 min):
    MODAL_PROFILE=aaron-j-wms modal deploy serve_rvc_modal.py
Then set MODAL_ENDPOINT_URL on the box to the printed *.modal.run base URL.
"""
import json
import subprocess
import tempfile
from pathlib import Path

import modal

APPLIO = "/Applio"
ALLOWED_VOICES = {"trump", "jfk", "obama", "mlk", "queen_elizabeth"}

# Same image train_rvc_modal.py uses — Applio + cu128 torch + baked pretrained
# weights — so inference matches training and cold starts don't re-download.
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "ffmpeg")
    .run_commands("git clone --depth 1 https://github.com/IAHispano/Applio.git /Applio")
    .run_commands(
        "cd /Applio && pip install -r requirements.txt "
        "--extra-index-url https://download.pytorch.org/whl/cu128"
    )
    .run_commands(
        "cd /Applio && python core.py prerequisites "
        "--models True --pretraineds_hifigan True --exe False"
    )
)

app = modal.App("voicemix-rvc")
vol = modal.Volume.from_name("rvc-vol")


def _ensure_applio_config() -> None:
    """Applio's CLI expects this UI config even headless (mirrors train_rvc_modal)."""
    config_path = Path(APPLIO) / "assets" / "config.json"
    if config_path.exists():
        return
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {
                "theme": {"file": "Applio.py", "class": "Applio"},
                "plugins": [],
                "discord_presence": False,
                "lang": {"override": False, "selected_lang": "en_US"},
                "version": "headless",
                "model_author": "None",
                "precision": "fp32",
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _convert(wav_bytes: bytes, voice: str, index_rate: float, pitch: int) -> bytes:
    """Run one RVC conversion: source WAV bytes -> target-timbre WAV bytes."""
    art = Path("/vol/artifacts") / voice
    pth = art / f"{voice}.pth"
    indexes = sorted(art.glob("*.index"), key=lambda f: f.stat().st_size, reverse=True)
    if not pth.exists() or not indexes:
        raise FileNotFoundError(f"no trained model on the volume for voice {voice!r}")
    index = indexes[0]  # the added_* retrieval index is the largest

    work = Path(tempfile.mkdtemp())
    src, out = work / "in.wav", work / "out.wav"
    src.write_bytes(wav_bytes)
    _ensure_applio_config()
    subprocess.run(
        f"python core.py infer --input_path {src} --output_path {out} "
        f"--pth_path {pth} --index_path {index} --f0_method rmvpe "
        f"--index_rate {index_rate} --pitch {pitch} --export_format WAV",
        shell=True,
        cwd=APPLIO,
        check=True,
    )
    return out.read_bytes()


# T4 chosen empirically: RVC inference is overhead-dominated (per-call model
# reload), not GPU-bound — T4/L4/A10G all measured ~15-17s on a short clip while
# A100 was pricier AND slower. T4 is cheapest + most abundant. max_inputs=1 keeps
# each GPU container doing one conversion at a time; Modal autoscales containers
# for concurrency. scaledown_window keeps a warm container 5 min to dodge cold starts.
@app.function(image=image, gpu="T4", volumes={"/vol": vol}, timeout=600, scaledown_window=300)
@modal.concurrent(max_inputs=1)
@modal.asgi_app()
def web():
    from fastapi import FastAPI, HTTPException, Request, Response
    from starlette.concurrency import run_in_threadpool

    api = FastAPI()

    @api.get("/health")
    async def health():
        return {"ok": True}

    @api.post("/convert")
    async def convert(request: Request, voice: str, index_rate: float = 0.5, pitch: int = 0):
        if voice not in ALLOWED_VOICES:
            raise HTTPException(404, f"unknown voice {voice!r}")
        wav = await request.body()
        if not wav:
            raise HTTPException(400, "empty request body")
        index_rate = max(0.0, min(1.0, index_rate))
        pitch = max(-24, min(24, int(pitch)))
        try:
            out = await run_in_threadpool(_convert, wav, voice, index_rate, pitch)
        except FileNotFoundError as e:
            raise HTTPException(404, str(e))
        except subprocess.CalledProcessError:
            raise HTTPException(500, "RVC inference failed")
        return Response(content=out, media_type="audio/wav")

    return api
