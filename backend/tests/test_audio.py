import io
import wave

import pytest


def make_wav(seconds: float = 0.5, rate: int = 8000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return buf.getvalue()


def test_normalize_produces_48k_mono_wav():
    # 48kHz full-band, not 16k: STS needs the consonant detail above 8kHz
    from app.audio import normalize_to_wav

    out = normalize_to_wav(make_wav())
    with wave.open(io.BytesIO(out), "rb") as w:
        assert w.getframerate() == 48000
        assert w.getnchannels() == 1


def test_normalize_rejects_garbage():
    from app.audio import AudioDecodeError, normalize_to_wav

    with pytest.raises(AudioDecodeError):
        normalize_to_wav(b"this is not audio at all")


def test_duration_seconds():
    from app.audio import duration_seconds, normalize_to_wav

    wav = normalize_to_wav(make_wav(seconds=2.0))
    assert duration_seconds(wav) == pytest.approx(2.0, abs=0.2)


def test_wav_to_mp3_roundtrip():
    from app.audio import normalize_to_wav, wav_to_mp3

    mp3 = wav_to_mp3(normalize_to_wav(make_wav()))
    assert len(mp3) > 0
    assert mp3 != b""


def test_placeholder_mp3():
    from app.audio import placeholder_mp3

    assert len(placeholder_mp3()) > 0
