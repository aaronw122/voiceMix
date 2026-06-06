def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_health_alias_for_deploy_pipeline(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_fake_engines_mode_runs_stub_for_all_voices(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("AUDIO_DIR", str(tmp_path / "audio"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "voicemix.db"))
    monkeypatch.setenv("BASE_URL", "http://testserver")
    monkeypatch.setenv("FAKE_ENGINES", "1")
    from app.engines import StubModalEngine
    from app.main import create_app

    app = create_app()
    assert isinstance(app.state.engines["elevenlabs"], StubModalEngine)

    # /convert works end-to-end with no API key in fake mode
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 4000)
    with TestClient(app) as client:
        resp = client.post(
            "/convert",
            files={"audio": ("rec.wav", buf.getvalue(), "audio/wav")},
            data={"voiceId": "old-man"},
        )
    assert resp.status_code == 200
    assert set(resp.json().keys()) == {"url", "title", "audioUrl"}
