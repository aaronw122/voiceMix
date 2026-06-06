import pytest
from fastapi.testclient import TestClient

FAKE_MP3 = b"ID3FAKE_MP3_BYTES"


class FakeEngine:
    """Test double for any VoiceEngine. Records the last call."""

    def __init__(self, output: bytes = FAKE_MP3):
        self.output = output
        self.last_call = None

    async def transform(self, wav, voice_id, text=None):
        self.last_call = {"wav": wav, "voice_id": voice_id, "text": text}
        return self.output


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIO_DIR", str(tmp_path / "audio"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "voicemix.db"))
    monkeypatch.setenv("BASE_URL", "http://testserver")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key-not-real")
    from app.main import create_app

    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)
