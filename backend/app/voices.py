# elevenVoiceId values are current ElevenLabs premade voices (per the elevenlabs/skills
# recommended list — the older Adam/Rachel legacy IDs are missing from newer accounts).
# Stock voices are placeholders until John's IVC clones land; scripts/smoke.py verifies
# the IDs against the real account.
VOICES = [
    {
        "id": "old-man",
        "name": "Old Man",
        "engine": "elevenlabs",
        "acceptsText": False,
        "elevenVoiceId": "pqHfZKP75CvOlQylNhV4",  # Bill — american, age=old ("Wise, Mature, Balanced")
    },
    {
        "id": "young-woman",
        "name": "Young Woman",
        "engine": "elevenlabs",
        "acceptsText": False,
        "elevenVoiceId": "EXAVITQu4vr4xnSDxMaL",  # Sarah
    },
    {
        "id": "jfk",
        "name": "JFK",
        "engine": "modal",
        "acceptsText": True,
        "elevenVoiceId": None,
    },
]

_PUBLIC_FIELDS = ("id", "name", "engine", "acceptsText")

# STS rendering defaults: higher stability = less phoneme drift/warble; high
# similarity_boost = closer to the target timbre. Per-voice overrides go in a
# "voiceSettings" key on the catalog entry (tune via the Tier-3 eval harness).
DEFAULT_VOICE_SETTINGS = {"stability": 0.65, "similarity_boost": 0.8, "style": 0.0}


def voice_settings_for(eleven_voice_id: str) -> dict:
    for v in VOICES:
        if v.get("elevenVoiceId") == eleven_voice_id:
            return {**DEFAULT_VOICE_SETTINGS, **v.get("voiceSettings", {})}
    return dict(DEFAULT_VOICE_SETTINGS)


def list_voices() -> list[dict]:
    return [{k: v[k] for k in _PUBLIC_FIELDS} for v in VOICES]


def get_voice(voice_id: str) -> dict | None:
    return next((v for v in VOICES if v["id"] == voice_id), None)
