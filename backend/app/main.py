import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db, storage
from .engines import (
    ElevenLabsEngine,
    ElevenLabsSttTtsEngine,
    GptSoVitsModalEngine,
    RvcModalEngine,
    StubModalEngine,
)
from .routes import router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    yield
    # close engines that own network clients (tests may swap in fakes without aclose)
    for engine in app.state.engines.values():
        aclose = getattr(engine, "aclose", None)
        if aclose is not None:
            await aclose()


def create_app() -> FastAPI:
    db.init_db()
    app = FastAPI(title="voiceMix", lifespan=_lifespan)
    if os.environ.get("FAKE_ENGINES") == "1":
        # keyless dev/demo-fallback mode: every voice runs the stub (passthrough audio)
        app.state.engines = {
            "elevenlabs": StubModalEngine(),
            "modal": StubModalEngine(),
            "tts_modal": StubModalEngine(),
        }
    else:
        # stt-tts (default): always-articulate output, loses sender's delivery.
        # ELEVENLABS_MODE=sts: keeps delivery but warbles on unclear input.
        sts_mode = os.environ.get("ELEVENLABS_MODE") == "sts"
        app.state.engines = {
            "elevenlabs": ElevenLabsEngine() if sts_mode else ElevenLabsSttTtsEngine(),
            # self-hosted RVC models (timbre swap) when the Modal endpoint is configured
            "modal": RvcModalEngine() if os.environ.get("MODAL_ENDPOINT_URL") else StubModalEngine(),
            # fine-tuned GPT-SoVITS ASR->TTS (currently trump); separate endpoint so RVC
            # stays the safe fallback for every other voice until each clears the quality gate
            "tts_modal": (
                GptSoVitsModalEngine() if os.environ.get("TTS_MODAL_ENDPOINT_URL") else StubModalEngine()
            ),
        }
    # The React SPA is served from a different origin (voicemix.awill.co) than the
    # API (voiceapi.awill.co) — ported from the placeholder backend Aaron wired for it.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://voicemix.awill.co", "http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    app.mount("/audio", StaticFiles(directory=storage.audio_dir()), name="audio")
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

    @app.get("/healthz")
    @app.get("/health")  # alias: deploy pipeline (Dockerfile HEALTHCHECK + CI gate) probes /health
    async def healthz():
        return {"ok": True}

    @app.exception_handler(HTTPException)
    async def error_shape(request, exc: HTTPException):
        logger.warning("%s %s -> %s: %s", request.method, request.url.path, exc.status_code, exc.detail)
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error_shape(request, exc: RequestValidationError):
        errors = exc.errors()
        msg = f"{errors[0]['loc'][-1]}: {errors[0]['msg']}" if errors else "Invalid request"
        logger.warning("%s %s -> 422 validation: %s", request.method, request.url.path, msg)
        return JSONResponse({"error": msg}, status_code=422)

    @app.exception_handler(Exception)
    async def unhandled_error_shape(request, exc: Exception):
        # keep the {"error": ...} contract even for bugs (e.g. corrupt DB rows)
        return JSONResponse({"error": "Internal server error"}, status_code=500)

    return app
