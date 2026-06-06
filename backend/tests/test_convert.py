import io
import wave

from tests.conftest import FAKE_MP3, FakeEngine


def make_wav(seconds: float = 0.5) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * int(8000 * seconds))
    return buf.getvalue()


def post_convert(client, voice_id="old-man", audio_bytes=None):
    return client.post(
        "/convert",
        files={"audio": ("rec.wav", audio_bytes or make_wav(), "audio/wav")},
        data={"voiceId": voice_id},
    )


def test_convert_happy_path(client, app):
    fake = FakeEngine()
    app.state.engines["elevenlabs"] = fake

    resp = post_convert(client)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"url", "title", "audioUrl"}
    assert body["title"] == "Old Man — voiceMix clip"
    assert "/share/" in body["url"]

    # the engine got the ELEVENLABS id, not the catalog id
    assert fake.last_call["voice_id"] == "JBFqnCBsd6RMkjVDRZzb"

    # the audioUrl actually serves the engine's MP3
    audio_resp = client.get(body["audioUrl"].replace("http://testserver", ""))
    assert audio_resp.status_code == 200
    assert audio_resp.content == FAKE_MP3


def test_unknown_voice_404(client):
    resp = post_convert(client, voice_id="not-a-voice")
    assert resp.status_code == 404
    assert "error" in resp.json()


def test_modal_voice_on_convert_422(client):
    resp = post_convert(client, voice_id="jfk")
    assert resp.status_code == 422
    assert "impersonate" in resp.json()["error"]


def test_oversize_upload_413(client):
    resp = post_convert(client, audio_bytes=b"\x00" * (10 * 1024 * 1024 + 1))
    assert resp.status_code == 413
    assert "error" in resp.json()


def test_garbage_audio_422(client):
    resp = post_convert(client, audio_bytes=b"definitely not audio")
    assert resp.status_code == 422
    assert resp.json()["error"] == "Couldn't read that recording"


def test_too_long_recording_422(client):
    resp = post_convert(client, audio_bytes=make_wav(seconds=61))
    assert resp.status_code == 422
    assert "1 minute" in resp.json()["error"]


def test_engine_failure_502(client, app):
    from app.engines import EngineError

    class ExplodingEngine:
        async def transform(self, wav, voice_id, text=None):
            raise EngineError("upstream sad")

    app.state.engines["elevenlabs"] = ExplodingEngine()
    resp = post_convert(client)
    assert resp.status_code == 502
    assert "error" in resp.json()
