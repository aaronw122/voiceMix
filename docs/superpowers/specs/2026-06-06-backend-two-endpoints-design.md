# voiceMix Backend — Two Convert Endpoints (Design)

**Date:** 2026-06-06
**Owner:** German
**Status:** Approved design, pre-implementation
**Supersedes (in part):** `plan.md` tech-stack rows for Metadata (Postgres) and Object store (MinIO) — see Decisions.

## Goal

Build the voiceMix backend: `POST /convert` (real, ElevenLabs STS) and `POST /impersonate`
(stubbed behind the same contract until John's Modal engine lands), plus `/voices`,
`/share/:id`, and static audio serving. The locked client contract from `plan.md` is
unchanged: both convert endpoints return `{ url, title, audioUrl }`.

## Decisions (deltas from plan.md)

| plan.md said | This design says | Why |
| --- | --- | --- |
| MinIO + presigned URLs | **Local disk + FastAPI StaticFiles** | On a single Hetzner box, MinIO adds a container, credentials, and presign plumbing for zero benefit — the bytes traverse the same NIC either way. The contract only requires that `audioUrl` is fetchable and that we persist a durable key, which a plain static URL satisfies. Swap path preserved behind a two-function storage interface. |
| Postgres (Docker) | **SQLite** | One 4-column table, one insert per clip. SQLite removes the last Docker dependency from local dev. |
| (gap — no catalog endpoint) | **`GET /voices`** | plan.md requires the picker catalog to carry `engine` and text-input flags but never says who serves it. Backend serves it: one source of truth for web + iMessage during the hour-6 voice swap. |
| Share page owner ambiguous | **Backend serves minimal HTML** | The fallback share link must render standalone. ~30-line server template with `<audio>` + OG meta tags; works the moment the backend works, no frontend dependency. React may add a prettier route later. |
| /impersonate engine | **Stub now, John plugs in** | German owns `/convert`; John ships the Whisper+TTS Modal engine into a `VoiceEngine` seam without touching anything else. |

## Architecture

```
client ──POST /convert or /impersonate──> FastAPI
                                            │ validate (≤1 min, ≤10 MB)
                                            │ audio.py: ffmpeg → WAV 48kHz mono
                                            │ engines.py: VoiceEngine.transform() → MP3 bytes
                                            │ storage.py: save → data/audio/<key>.mp3
                                            │ db.py: INSERT clip row (SQLite)
                                            └─> { url, title, audioUrl }

client ──GET audioUrl──> StaticFiles mount at /audio (same app)
anyone ──GET /share/:id──> server-rendered HTML (title + <audio> + OG tags)
client ──GET /voices──> JSON catalog
```

Local dev: `uvicorn app.main:app` with ffmpeg on PATH. No containers.
Deploy (later pass): the existing Docker Compose + Caddy plan, with one volume for `data/`.

## Repo layout

```
backend/
├── app/
│   ├── main.py          # FastAPI app, StaticFiles mount, startup db init
│   ├── routes.py        # /convert /impersonate /voices /share
│   ├── engines.py       # VoiceEngine Protocol + ElevenLabsEngine, StubModalEngine
│   ├── audio.py         # ffmpeg normalize + duration check (subprocess)
│   ├── storage.py       # save(bytes) -> key, url_for(key) -> str
│   ├── db.py            # SQLite: clips table
│   ├── voices.py        # catalog: id, name, engine, acceptsText, elevenVoiceId
│   └── templates/share.html
├── tests/
├── scripts/smoke.py     # real-key ElevenLabs smoke test (manual)
├── pyproject.toml
└── .env.example         # ELEVENLABS_API_KEY, BASE_URL
```

## Endpoints

| Route | In | Out |
| --- | --- | --- |
| `POST /convert` | multipart: `audio` (webm/m4a/wav, ≤1 min, ≤10 MB), `voiceId` | `{ url, title, audioUrl }` |
| `POST /impersonate` | multipart: `voiceId` + exactly one of `audio` / `text` | same shape |
| `GET /voices` | — | `[{ id, name, engine, acceptsText }]` |
| `GET /share/{id}` | — | HTML page (title, `<audio>`, OG tags); 404 page for unknown id |
| `GET /audio/{key}.mp3` | — | MP3 bytes via StaticFiles |

- `url` = `{BASE_URL}/share/{id}`
- `audioUrl` = `{BASE_URL}/audio/{key}.mp3`
- `title` = voice display name + short human label (e.g. "Old Man — voiceMix clip")
- Clients route by the catalog's `engine` field: `"elevenlabs"` → `/convert`, `"modal"` → `/impersonate`.

## Engine seam

```python
class VoiceEngine(Protocol):
    async def transform(self, wav: bytes | None, voice_id: str, text: str | None) -> bytes:
        """Exactly one of wav/text is provided (routes enforce this). Output: MP3 bytes."""
```

- **ElevenLabsEngine** (real, German): calls ElevenLabs speech-to-speech with the mapped
  `elevenVoiceId`, returns MP3 bytes. API key from `ELEVENLABS_API_KEY`.
- **StubModalEngine** (placeholder, replaced by John): validates inputs and returns a canned
  MP3 (or the input transcoded to MP3) so clients exercise realistic flow/latency. John
  replaces this class with the Whisper + CosyVoice2/GPT-SoVITS Modal client; routing,
  storage, db, and the contract are untouched.

Routing is fixed: `/convert` → ElevenLabsEngine, `/impersonate` → modal engine.

## Data & storage

- `storage.py`: `save(data: bytes) -> key` writes `data/audio/{uuid}.mp3`;
  `url_for(key) -> str` returns `{BASE_URL}/audio/{key}.mp3`. Moving to S3/Hetzner Object
  Storage later = a second implementation of these two functions.
- `db.py`: single table
  `clips(id TEXT PRIMARY KEY, title TEXT, object_key TEXT, content_type TEXT, created_at TEXT)`.
  Persist the durable `object_key`, never a full URL (same principle as plan.md).
- No TTL (per plan.md: ~1 MB/clip, 75 GB box ≈ 75k clips).

## Validation & errors

| Condition | Response |
| --- | --- |
| Upload > 10 MB | 413 |
| Duration > 60 s (via ffprobe after upload) | 422 |
| Unknown `voiceId` | 404 |
| `voiceId` routed to the wrong endpoint (e.g. modal voice sent to `/convert`) | 422 |
| `/impersonate` with both or neither of `audio`/`text` | 422 |
| ffmpeg cannot decode input | 422 ("couldn't read that recording") |
| ElevenLabs/engine failure | 502 with JSON error body clients can display |

All errors return `{ "error": "<human-readable message>" }`.

## Testing

- TDD with pytest + httpx `AsyncClient` against the app.
- Engine boundary mocked with a `FakeEngine` returning known MP3 bytes — unit/integration
  tests never hit the network or need an API key.
- ffmpeg tests use tiny generated fixtures (e.g. `ffmpeg`-synthesized sine-wave webm/m4a).
- `scripts/smoke.py`: manual, real-key, one round-trip through ElevenLabs STS to prove the
  live integration. **Prerequisite:** ElevenLabs API key (open TODO in plan.md) — needed
  before the smoke test, not before development.

## Out of scope (this pass)

Real Modal engine (John), auth, rate limiting, TTL/cleanup, Postgres migration, Caddy +
Docker Compose deploy wiring (next pass), IVC voice-cloning workflow (offline, separate
from serving), the web frontend and iMessage clients.
