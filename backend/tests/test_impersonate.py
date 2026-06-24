from tests.conftest import FAKE_MP3, FakeEngine
from tests.test_convert import make_wav


def test_impersonate_with_audio(client, app):
    fake = FakeEngine()
    app.state.engines["tts_modal"] = fake

    resp = client.post(
        "/impersonate",
        files={"audio": ("rec.wav", make_wav(), "audio/wav")},
        data={"voiceId": "trump"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"url", "title", "audioUrl"}
    assert body["title"] == "Trump — voiceMix clip"
    assert fake.last_call["wav"] is not None
    assert fake.last_call["text"] is None


def test_impersonate_with_text(client, app):
    fake = FakeEngine()
    app.state.engines["tts_modal"] = fake

    resp = client.post("/impersonate", data={"voiceId": "trump", "text": "make it great"})
    assert resp.status_code == 200
    assert fake.last_call == {"wav": None, "voice_id": "trump", "text": "make it great"}


def test_trump_routes_to_tts_engine(client, app):
    # trump (modalEngine="tts") must hit the shared fine-tuned endpoint ("tts_modal"),
    # not the bare "modal" fallback.
    fallback = FakeEngine(b"FALLBACK")
    tts = FakeEngine(b"TTS")
    app.state.engines["modal"] = fallback
    app.state.engines["tts_modal"] = tts

    resp = client.post(
        "/impersonate",
        files={"audio": ("rec.wav", make_wav(), "audio/wav")},
        data={"voiceId": "trump"},
    )
    assert resp.status_code == 200
    assert tts.last_call is not None and tts.last_call["voice_id"] == "trump"
    assert fallback.last_call is None  # trump must not touch the bare modal fallback


def test_dwarkesh_routes_to_tts_dwarkesh_engine(client, app):
    # dwarkesh (modalEngine="tts_dwarkesh") must hit its OWN dedicated F5 container,
    # not the shared trump endpoint ("tts_modal") and not the bare "modal" fallback.
    fallback = FakeEngine(b"FALLBACK")
    tts = FakeEngine(b"TTS")
    dwarkesh = FakeEngine(b"DWARKESH")
    app.state.engines["modal"] = fallback
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
    assert fallback.last_call is None  # dwarkesh must not touch the bare modal fallback


def test_elon_routes_to_tts_elon_engine(client, app):
    # elon (modalEngine="tts_elon") must hit its OWN dedicated F5 container,
    # not the shared trump endpoint ("tts_modal") and not the bare "modal" fallback.
    fallback = FakeEngine(b"FALLBACK")
    tts = FakeEngine(b"TTS")
    elon = FakeEngine(b"ELON")
    app.state.engines["modal"] = fallback
    app.state.engines["tts_modal"] = tts
    app.state.engines["tts_elon"] = elon

    resp = client.post(
        "/impersonate",
        files={"audio": ("rec.wav", make_wav(), "audio/wav")},
        data={"voiceId": "elon"},
    )
    assert resp.status_code == 200
    assert elon.last_call is not None and elon.last_call["voice_id"] == "elon"
    assert tts.last_call is None  # elon must not touch trump's shared endpoint
    assert fallback.last_call is None  # elon must not touch the bare modal fallback


def test_impersonate_requires_exactly_one_input(client):
    # neither
    resp = client.post("/impersonate", data={"voiceId": "trump"})
    assert resp.status_code == 422
    # both
    resp = client.post(
        "/impersonate",
        files={"audio": ("rec.wav", make_wav(), "audio/wav")},
        data={"voiceId": "trump", "text": "make it great"},
    )
    assert resp.status_code == 422


def test_empty_text_field_counts_as_absent(client):
    # browser forms submit empty fields as "" — neither input provided
    resp = client.post("/impersonate", data={"voiceId": "trump", "text": ""})
    assert resp.status_code == 422
    assert "exactly one" in resp.json()["error"]


def test_impersonate_engine_failure_502(client, app):
    from app.engines import EngineError

    class ExplodingEngine:
        async def transform(self, wav, voice_id, text=None):
            raise EngineError("upstream sad")

    app.state.engines["tts_modal"] = ExplodingEngine()
    resp = client.post("/impersonate", data={"voiceId": "trump", "text": "make it great"})
    assert resp.status_code == 502
    assert "error" in resp.json()


def test_elevenlabs_voice_on_impersonate_422(client):
    resp = client.post("/impersonate", data={"voiceId": "old-man", "text": "hi"})
    assert resp.status_code == 422


def test_impersonate_unknown_voice_404(client):
    resp = client.post("/impersonate", data={"voiceId": "elvis", "text": "hi"})
    assert resp.status_code == 404


def test_warm_routes_to_voices_own_engine(client, app):
    # /warm must pre-warm the SAME engine /impersonate would use for that voice.
    tts = FakeEngine()
    dwarkesh = FakeEngine()
    app.state.engines["tts_modal"] = tts
    app.state.engines["tts_dwarkesh"] = dwarkesh

    resp = client.post("/warm", data={"voiceId": "dwarkesh"})
    assert resp.status_code == 202
    assert dwarkesh.warm_calls == 1
    assert tts.warm_calls == 0  # only the target voice's container is warmed


def test_warm_elevenlabs_voice_is_noop_202(client):
    # elevenlabs voices have no cold-start — warm is a 202 no-op, never an error.
    resp = client.post("/warm", data={"voiceId": "old-man"})
    assert resp.status_code == 202


def test_warm_unknown_voice_202(client):
    # warming is best-effort: an unknown voice must not 404 / break the recording flow.
    resp = client.post("/warm", data={"voiceId": "elvis"})
    assert resp.status_code == 202
