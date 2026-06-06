from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import db, storage
from .engines import ElevenLabsEngine, StubModalEngine
from .routes import router


def create_app() -> FastAPI:
    db.init_db()
    app = FastAPI(title="voiceMix")
    app.state.engines = {
        "elevenlabs": ElevenLabsEngine(),
        "modal": StubModalEngine(),
    }
    app.include_router(router)
    app.mount("/audio", StaticFiles(directory=storage.audio_dir()), name="audio")

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    return app
