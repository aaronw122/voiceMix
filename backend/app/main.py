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
