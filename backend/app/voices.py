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
    # Celebrity voices: self-hosted Modal models, all behind /impersonate. modalEngine
    # selects the backend: "rvc" = timbre swap (keeps YOUR delivery, audio only) while
    # "tts" = fine-tuned GPT-SoVITS ASR->TTS (target's full accent/cadence, audio or text).
    # trump migrated to the stronger TTS path; the rest stay on RVC until they clear the gate.
    # NOTE: trump acceptsText stays False until Aaron OKs exposing typed input in the UI —
    # the tts engine already supports text, this flag only gates the frontend affordance.
    {"id": "jfk", "name": "JFK", "engine": "modal", "modalEngine": "rvc", "acceptsText": False, "elevenVoiceId": None},
    {"id": "trump", "name": "Trump", "engine": "modal", "modalEngine": "tts", "acceptsText": False, "elevenVoiceId": None},
    {"id": "obama", "name": "Obama", "engine": "modal", "modalEngine": "rvc", "acceptsText": False, "elevenVoiceId": None},
    {"id": "mlk", "name": "MLK", "engine": "modal", "modalEngine": "rvc", "acceptsText": False, "elevenVoiceId": None},
    {"id": "queen_elizabeth", "name": "Queen Elizabeth", "engine": "modal", "modalEngine": "rvc", "acceptsText": False, "elevenVoiceId": None},
]

_PUBLIC_FIELDS = ("id", "name", "engine", "acceptsText")


def list_voices() -> list[dict]:
    return [{k: v[k] for k in _PUBLIC_FIELDS} for v in VOICES]


def get_voice(voice_id: str) -> dict | None:
    return next((v for v in VOICES if v["id"] == voice_id), None)
