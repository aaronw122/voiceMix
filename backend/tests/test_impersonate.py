from tests.conftest import FAKE_MP3, FakeEngine
from tests.test_convert import make_wav


def test_impersonate_with_audio(client, app):
    fake = FakeEngine()
    app.state.engines["modal"] = fake

    resp = client.post(
        "/impersonate",
        files={"audio": ("rec.wav", make_wav(), "audio/wav")},
        data={"voiceId": "jfk"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"url", "title", "audioUrl"}
    assert body["title"] == "JFK — voiceMix clip"
    assert fake.last_call["wav"] is not None
    assert fake.last_call["text"] is None


def test_impersonate_with_text(client, app):
    fake = FakeEngine()
    app.state.engines["modal"] = fake

    resp = client.post("/impersonate", data={"voiceId": "jfk", "text": "ask not"})
    assert resp.status_code == 200
    assert fake.last_call == {"wav": None, "voice_id": "jfk", "text": "ask not"}


def test_impersonate_requires_exactly_one_input(client):
    # neither
    resp = client.post("/impersonate", data={"voiceId": "jfk"})
    assert resp.status_code == 422
    # both
    resp = client.post(
        "/impersonate",
        files={"audio": ("rec.wav", make_wav(), "audio/wav")},
        data={"voiceId": "jfk", "text": "ask not"},
    )
    assert resp.status_code == 422


def test_elevenlabs_voice_on_impersonate_422(client):
    resp = client.post("/impersonate", data={"voiceId": "old-man", "text": "hi"})
    assert resp.status_code == 422


def test_impersonate_unknown_voice_404(client):
    resp = client.post("/impersonate", data={"voiceId": "elvis", "text": "hi"})
    assert resp.status_code == 404
