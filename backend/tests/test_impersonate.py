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


def test_trump_routes_to_tts_engine(client, app):
    # per-voice migration: trump (modalEngine="tts") must hit the GPT-SoVITS endpoint,
    # not the RVC "modal" engine that the other celebrity voices still use.
    rvc = FakeEngine(b"RVC")
    tts = FakeEngine(b"TTS")
    app.state.engines["modal"] = rvc
    app.state.engines["tts_modal"] = tts

    resp = client.post(
        "/impersonate",
        files={"audio": ("rec.wav", make_wav(), "audio/wav")},
        data={"voiceId": "trump"},
    )
    assert resp.status_code == 200
    assert tts.last_call is not None and tts.last_call["voice_id"] == "trump"
    assert rvc.last_call is None  # trump must not touch the RVC engine


def test_dwarkesh_routes_to_tts_dwarkesh_engine(client, app):
    # dwarkesh (modalEngine="tts_dwarkesh") must hit its OWN dedicated F5 container,
    # not the shared trump endpoint ("tts_modal") and not the RVC fallback ("modal").
    rvc = FakeEngine(b"RVC")
    tts = FakeEngine(b"TTS")
    dwarkesh = FakeEngine(b"DWARKESH")
    app.state.engines["modal"] = rvc
    app.state.engines["tts_modal"] = tts
    app.state.engines["tts_dwarkesh"] = dwarkesh

    resp = client.post(
        "/impersonate",
        files={"audio": ("rec.wav", make_wav(), "audio/wav")},
        data={"voiceId": "dwarkesh"},
    )
    assert resp.status_code == 200
    assert dwarkesh.last_call is not None and dwarkesh.last_call["voice_id"] == "dwarkesh"
    assert tts.last_call is None  # dwarkesh must not touch trump's shared endpoint
    assert rvc.last_call is None  # dwarkesh must not touch the RVC engine


def test_jfk_still_routes_to_rvc_engine(client, app):
    rvc = FakeEngine(b"RVC")
    tts = FakeEngine(b"TTS")
    app.state.engines["modal"] = rvc
    app.state.engines["tts_modal"] = tts

    resp = client.post(
        "/impersonate",
        files={"audio": ("rec.wav", make_wav(), "audio/wav")},
        data={"voiceId": "jfk"},
    )
    assert resp.status_code == 200
    assert rvc.last_call is not None and rvc.last_call["voice_id"] == "jfk"
    assert tts.last_call is None


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


def test_empty_text_field_counts_as_absent(client):
    # browser forms submit empty fields as "" — neither input provided
    resp = client.post("/impersonate", data={"voiceId": "jfk", "text": ""})
    assert resp.status_code == 422
    assert "exactly one" in resp.json()["error"]


def test_impersonate_engine_failure_502(client, app):
    from app.engines import EngineError

    class ExplodingEngine:
        async def transform(self, wav, voice_id, text=None):
            raise EngineError("upstream sad")

    app.state.engines["modal"] = ExplodingEngine()
    resp = client.post("/impersonate", data={"voiceId": "jfk", "text": "ask not"})
    assert resp.status_code == 502
    assert "error" in resp.json()


def test_elevenlabs_voice_on_impersonate_422(client):
    resp = client.post("/impersonate", data={"voiceId": "old-man", "text": "hi"})
    assert resp.status_code == 422


def test_impersonate_unknown_voice_404(client):
    resp = client.post("/impersonate", data={"voiceId": "elvis", "text": "hi"})
    assert resp.status_code == 404
