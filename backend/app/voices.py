VOICES = [
    {
        "id": "old-man",
        "name": "Old Man",
        "engine": "elevenlabs",
        "acceptsText": False,
        "elevenVoiceId": "pNInz6obpgDQGcFmaJgB",
    },
    {
        "id": "young-woman",
        "name": "Young Woman",
        "engine": "elevenlabs",
        "acceptsText": False,
        "elevenVoiceId": "21m00Tcm4TlvDq8ikWAM",
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


def list_voices() -> list[dict]:
    return [{k: v[k] for k in _PUBLIC_FIELDS} for v in VOICES]


def get_voice(voice_id: str) -> dict | None:
    return next((v for v in VOICES if v["id"] == voice_id), None)
