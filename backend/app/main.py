import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db, storage
from .engines import ElevenLabsEngine, StubModalEngine
from .routes import router


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
        app.state.engines = {"elevenlabs": StubModalEngine(), "modal": StubModalEngine()}
    else:
        app.state.engines = {
            "elevenlabs": ElevenLabsEngine(),
            "modal": StubModalEngine(),
        }
    app.include_router(router)
    app.mount("/audio", StaticFiles(directory=storage.audio_dir()), name="audio")
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

    @app.get("/healthz")
    @app.get("/health")  # alias: deploy pipeline (Dockerfile HEALTHCHECK + CI gate) probes /health
    async def healthz():
        return {"ok": True}

    @app.exception_handler(HTTPException)
    async def error_shape(request, exc: HTTPException):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error_shape(request, exc: RequestValidationError):
        errors = exc.errors()
        msg = f"{errors[0]['loc'][-1]}: {errors[0]['msg']}" if errors else "Invalid request"
        return JSONResponse({"error": msg}, status_code=422)

    @app.exception_handler(Exception)
    async def unhandled_error_shape(request, exc: Exception):
        # keep the {"error": ...} contract even for bugs (e.g. corrupt DB rows)
        return JSONResponse({"error": "Internal server error"}, status_code=500)

    return app
