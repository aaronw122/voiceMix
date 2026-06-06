def test_save_and_url_for(app, monkeypatch):
    from app import storage

    key = storage.save(b"mp3-bytes-here")
    assert key  # uuid hex
    assert storage.url_for(key) == f"http://testserver/audio/{key}.mp3"


def test_saved_audio_served_via_static_mount(client):
    from app import storage

    key = storage.save(b"mp3-bytes-here")
    resp = client.get(f"/audio/{key}.mp3")
    assert resp.status_code == 200
    assert resp.content == b"mp3-bytes-here"
