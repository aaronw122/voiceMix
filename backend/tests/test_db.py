def test_insert_and_get_clip(app):
    from app import db

    db.insert_clip("abc123", "Old Man — voiceMix clip", "deadbeef")
    clip = db.get_clip("abc123")
    assert clip["id"] == "abc123"
    assert clip["title"] == "Old Man — voiceMix clip"
    assert clip["object_key"] == "deadbeef"
    assert clip["content_type"] == "audio/mpeg"
    assert clip["created_at"]  # ISO timestamp


def test_get_missing_clip_returns_none(app):
    from app import db

    assert db.get_clip("nope") is None
