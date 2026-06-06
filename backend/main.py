from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="voiceMix backend")

# The SPA is served from a different origin (voicemix.awill.co) than the API
# (voiceapi.awill.co), so the browser needs explicit CORS permission to call it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://voicemix.awill.co",
        "http://localhost:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {"service": "voicemix-backend"}
