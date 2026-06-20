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
        "id": "femme-fatale",
        "name": "Femme Fatale",
        "engine": "elevenlabs",
        "acceptsText": False,
        "elevenVoiceId": "eVItLK1UvXctxuaRV2Oq",  # Jean — library voice added to account
    },
    # Self-hosted fine-tuned voices on Modal, behind /impersonate. modalEngine selects the
    # container: "tts" -> the Trump F5/GPT-SoVITS endpoint; "tts_dwarkesh" -> the dedicated
    # Dwarkesh F5 container; "tts_elon" -> the dedicated Elon F5 container. Each regenerates the
    # words in the target's FULL delivery (accent + cadence), audio or text. NOTE: acceptsText
    # stays False until Aaron OKs exposing typed input in the UI — the engines already support
    # text; this flag only gates the affordance.
    {"id": "trump", "name": "Trump", "engine": "modal", "modalEngine": "tts", "acceptsText": False, "elevenVoiceId": None},
    {"id": "dwarkesh", "name": "Dwarkesh", "engine": "modal", "modalEngine": "tts_dwarkesh", "acceptsText": False, "elevenVoiceId": None},
    {"id": "elon", "name": "Elon", "engine": "modal", "modalEngine": "tts_elon", "acceptsText": False, "elevenVoiceId": None},
]

_PUBLIC_FIELDS = ("id", "name", "engine", "acceptsText")


def list_voices() -> list[dict]:
    return [{k: v[k] for k in _PUBLIC_FIELDS} for v in VOICES]


def get_voice(voice_id: str) -> dict | None:
    return next((v for v in VOICES if v["id"] == voice_id), None)
