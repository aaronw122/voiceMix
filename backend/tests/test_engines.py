import asyncio

import httpx
import pytest


def test_elevenlabs_engine_posts_sts_and_returns_mp3(monkeypatch):
    from app.engines import ElevenLabsEngine

    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["api_key"] = request.headers.get("xi-api-key")
        seen["body"] = request.read()
        return httpx.Response(200, content=b"MP3_FROM_ELEVENLABS")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    engine = ElevenLabsEngine(client=client)
    out = asyncio.run(engine.transform(b"WAVBYTES", "pNInz6obpgDQGcFmaJgB", None))

    assert out == b"MP3_FROM_ELEVENLABS"
    assert "speech-to-speech/pNInz6obpgDQGcFmaJgB" in seen["url"]
    assert seen["api_key"] == "test-key"
    # pin the English STS model — multilingual drifted accent/language in testing
    assert b"eleven_english_sts_v2" in seen["body"]


def test_elevenlabs_engine_raises_on_api_error(monkeypatch):
    from app.engines import ElevenLabsEngine, EngineError

    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(401, text="bad key"))
    )
    engine = ElevenLabsEngine(client=client)
    with pytest.raises(EngineError):
        asyncio.run(engine.transform(b"WAVBYTES", "voice", None))


def test_stub_modal_engine_transcodes_audio():
    import io
    import wave

    from app.engines import StubModalEngine

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 8000)

    out = asyncio.run(StubModalEngine().transform(buf.getvalue(), "jfk", None))
    assert len(out) > 0


def test_stub_modal_engine_handles_text_only():
    from app.engines import StubModalEngine

    out = asyncio.run(StubModalEngine().transform(None, "jfk", "ask not"))
    assert len(out) > 0
