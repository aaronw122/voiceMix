from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
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
    app.state.engines = {
        "elevenlabs": ElevenLabsEngine(),
        "modal": StubModalEngine(),
    }
    app.include_router(router)
    app.mount("/audio", StaticFiles(directory=storage.audio_dir()), name="audio")

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    @app.exception_handler(HTTPException)
    async def error_shape(request, exc: HTTPException):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)

    return app
