def test_share_page_renders(client, app):
    from app import db, storage

    key = storage.save(b"mp3")
    db.insert_clip("clip12345", "Old Man — voiceMix clip", key)

    resp = client.get("/share/clip12345")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    html = resp.text
    assert "Old Man — voiceMix clip" in html
    assert f"/audio/{key}.mp3" in html
    assert "<audio" in html
    assert 'property="og:title"' in html


def test_share_unknown_id_404(client):
    resp = client.get("/share/nope")
    assert resp.status_code == 404


def test_url_for_rejects_path_traversal_keys(app):
    import pytest

    from app import storage

    for bad in ("../etc/passwd", "a/b", "a\\b"):
        with pytest.raises(ValueError):
            storage.url_for(bad)
