from fastapi import FastAPI

app = FastAPI(title="voiceMix backend")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {"service": "voicemix-backend"}
