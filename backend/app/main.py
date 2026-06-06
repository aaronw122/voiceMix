from fastapi import FastAPI

from .routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="voiceMix")
    app.include_router(router)

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    return app
