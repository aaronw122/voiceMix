from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="voiceMix")

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    return app
