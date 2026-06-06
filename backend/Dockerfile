FROM python:3.12-slim

# ffmpeg: server-side normalization of browser-native recordings (webm/m4a/wav -> canonical WAV)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# deps first (cached layer), app code second
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app

ENV PATH="/app/.venv/bin:$PATH" \
    AUDIO_DIR=/data/audio \
    DB_PATH=/data/voicemix.db

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# --proxy-headers: honor X-Forwarded-Proto from cloudflared so request-derived
# URLs are https (mixed-content blocks http audio fetches from https pages)
CMD ["uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
