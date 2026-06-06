"""Manual smoke test: one real round-trip through ElevenLabs STS.

Usage:
    cd backend
    ELEVENLABS_API_KEY=sk_... uv run python scripts/smoke.py

Verifies: the API key works, the catalog's elevenVoiceId values exist on this
account, and STS returns playable MP3 bytes.
"""

import asyncio
import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.audio import placeholder_mp3, normalize_to_wav  # noqa: E402
from app.engines import ElevenLabsEngine  # noqa: E402
from app.voices import VOICES  # noqa: E402


async def main() -> None:
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        sys.exit("Set ELEVENLABS_API_KEY first")

    # 1. List account voices; check our catalog ids exist
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            "https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": key}
        )
        resp.raise_for_status()
        account_ids = {v["voice_id"] for v in resp.json()["voices"]}
    for v in VOICES:
        if v["engine"] == "elevenlabs":
            status = "OK" if v["elevenVoiceId"] in account_ids else "MISSING — fix voices.py"
            print(f"  {v['id']:<14} {v['elevenVoiceId']}: {status}")

    # 2. One real STS round-trip with a synthesized input clip
    wav = normalize_to_wav(placeholder_mp3(seconds=2.0))
    engine = ElevenLabsEngine()
    voice = next(v for v in VOICES if v["engine"] == "elevenlabs")
    mp3 = await engine.transform(wav, voice["elevenVoiceId"], None)
    out = "smoke_output.mp3"
    with open(out, "wb") as f:
        f.write(mp3)
    print(f"STS round-trip OK -> {out} ({len(mp3)} bytes). Play it to confirm.")


if __name__ == "__main__":
    asyncio.run(main())
