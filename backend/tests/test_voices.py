def test_voices_returns_catalog(client):
    resp = client.get("/voices")
    assert resp.status_code == 200
    voices = resp.json()
    assert len(voices) >= 2
    for v in voices:
        assert set(v.keys()) == {"id", "name", "engine", "acceptsText"}
        assert v["engine"] in ("elevenlabs", "modal")
    # internal ElevenLabs IDs must NOT leak to clients
    assert all("elevenVoiceId" not in v for v in voices)


def test_catalog_has_both_engines(client):
    engines = {v["engine"] for v in client.get("/voices").json()}
    assert engines == {"elevenlabs", "modal"}
