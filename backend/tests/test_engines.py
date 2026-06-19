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
    # quality params: 192kbps output; deliberately NO voice_settings (A/B-tested
    # worse than API defaults — see commit history)
    assert "output_format=mp3_44100_192" in seen["url"]
    assert b"voice_settings" not in seen["body"]


def test_elevenlabs_engine_raises_on_api_error(monkeypatch):
    from app.engines import ElevenLabsEngine, EngineError

    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(401, text="bad key"))
    )
    engine = ElevenLabsEngine(client=client)
    with pytest.raises(EngineError):
        asyncio.run(engine.transform(b"WAVBYTES", "voice", None))


def _stt_tts_transport(seen, stt_response=None, tts_status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "speech-to-text" in url:
            seen["stt_body"] = request.read()
            return stt_response or httpx.Response(200, json={"text": "hello there"})
        seen["tts_url"] = url
        seen["tts_json"] = request.read()
        return httpx.Response(tts_status, content=b"MP3_FROM_TTS")

    return httpx.MockTransport(handler)


def test_stt_tts_engine_transcribes_then_synthesizes(monkeypatch):
    from app.engines import ElevenLabsSttTtsEngine

    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    seen = {}
    engine = ElevenLabsSttTtsEngine(client=httpx.AsyncClient(transport=_stt_tts_transport(seen)))
    out = asyncio.run(engine.transform(b"WAVBYTES", "pqHfZKP75CvOlQylNhV4", None))

    assert out == b"MP3_FROM_TTS"
    assert b"scribe_v2" in seen["stt_body"]
    assert "text-to-speech/pqHfZKP75CvOlQylNhV4" in seen["tts_url"]
    assert "output_format=mp3_44100_192" in seen["tts_url"]
    assert b"hello there" in seen["tts_json"]  # the transcript is what gets spoken


def test_stt_tts_engine_text_input_skips_stt(monkeypatch):
    from app.engines import ElevenLabsSttTtsEngine

    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    seen = {}
    engine = ElevenLabsSttTtsEngine(client=httpx.AsyncClient(transport=_stt_tts_transport(seen)))
    out = asyncio.run(engine.transform(None, "voice", "typed words"))

    assert out == b"MP3_FROM_TTS"
    assert "stt_body" not in seen  # STT hop skipped entirely
    assert b"typed words" in seen["tts_json"]


def test_stt_tts_engine_empty_transcript_raises(monkeypatch):
    from app.engines import ElevenLabsSttTtsEngine, EngineError

    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    seen = {}
    transport = _stt_tts_transport(seen, stt_response=httpx.Response(200, json={"text": "  "}))
    engine = ElevenLabsSttTtsEngine(client=httpx.AsyncClient(transport=transport))
    with pytest.raises(EngineError):
        asyncio.run(engine.transform(b"WAVBYTES", "voice", None))


def test_stt_tts_engine_tts_error_raises(monkeypatch):
    from app.engines import ElevenLabsSttTtsEngine, EngineError

    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    engine = ElevenLabsSttTtsEngine(
        client=httpx.AsyncClient(transport=_stt_tts_transport({}, tts_status=429))
    )
    with pytest.raises(EngineError):
        asyncio.run(engine.transform(b"WAVBYTES", "voice", None))


def _tiny_wav(seconds: float = 0.5) -> bytes:
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * int(8000 * seconds))
    return buf.getvalue()


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


def test_gptsovits_engine_text_skips_audio_body():
    from app.engines import GptSoVitsModalEngine

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.read()
        return httpx.Response(200, content=b"MP3_FROM_TTS")

    engine = GptSoVitsModalEngine(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        base_url="http://tts.test",
    )
    out = asyncio.run(engine.transform(None, "trump", "make america"))

    assert out == b"MP3_FROM_TTS"  # Modal returns MP3 directly — no re-encode
    assert "/synthesize" in seen["url"]
    assert "voice=trump" in seen["url"] and "text=make+america" in seen["url"]
    assert seen["body"] == b""  # text path sends no audio


def test_gptsovits_engine_audio_posts_raw_wav():
    from app.engines import GptSoVitsModalEngine

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["ctype"] = request.headers.get("content-type")
        seen["body"] = request.read()
        return httpx.Response(200, content=b"MP3_FROM_TTS")

    engine = GptSoVitsModalEngine(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        base_url="http://tts.test",
    )
    out = asyncio.run(engine.transform(b"WAVBYTES", "trump", None))

    assert out == b"MP3_FROM_TTS"
    assert seen["ctype"] == "audio/wav"
    assert seen["body"] == b"WAVBYTES"  # raw body, not multipart


def test_gptsovits_engine_raises_on_error_status():
    from app.engines import EngineError, GptSoVitsModalEngine

    engine = GptSoVitsModalEngine(
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(500, text="boom"))
        ),
        base_url="http://tts.test",
    )
    with pytest.raises(EngineError):
        asyncio.run(engine.transform(None, "trump", "hi"))
