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
    assert fake.last_call["voice_id"] == "pNInz6obpgDQGcFmaJgB"

    # the audioUrl actually serves the engine's MP3
    audio_resp = client.get(body["audioUrl"].replace("http://testserver", ""))
    assert audio_resp.status_code == 200
    assert audio_resp.content == FAKE_MP3
