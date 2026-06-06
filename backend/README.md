# voiceMix backend

FastAPI service: `/convert` (ElevenLabs STS), `/impersonate` (stub → John's Modal engine),
`/voices`, `/share/:id`, static `/audio/*`. Spec: `../docs/superpowers/specs/2026-06-06-backend-two-endpoints-design.md`.

## Run

    brew install ffmpeg          # once
    cd backend
    uv sync
    cp .env.example .env         # add the real ELEVENLABS_API_KEY
    set -a; source .env; set +a
    uv run uvicorn --factory app.main:create_app --reload

## Test

    uv run pytest                          # no network, no key needed
    uv run python scripts/smoke.py         # manual: real ElevenLabs round-trip

## John: plugging in the Modal engine

Replace `StubModalEngine` in `app/engines.py` with a class implementing:

    async def transform(self, wav: bytes | None, voice_id: str, text: str | None) -> bytes

`voice_id` is the catalog id from `app/voices.py` (e.g. "jfk"); exactly one of
`wav`/`text` is non-None; return MP3 bytes. Raise `EngineError` on failure → the
route returns a clean 502. Nothing else needs to change.

## ElevenLabs integration notes

Follows the conventions from the `elevenlabs/skills` agents skill (`.agents/skills/agents/`):
`ELEVENLABS_API_KEY` env var, `xi-api-key` header, `https://api.elevenlabs.io/v1` base, and
current premade voice IDs (George/Sarah — the legacy Adam/Rachel IDs are missing from newer
accounts). We deliberately call the REST API via httpx instead of the `elevenlabs` Python SDK:
the engine seam is two HTTP calls, and `MockTransport` tests verify the actual wire format
(URL, header, multipart). Swap to the SDK inside `ElevenLabsEngine` if it ever grows. The
skill's Agents-Platform features (conversational agents, workflows, guardrails, widgets) are
N/A — this service is a one-shot speech-to-speech pipeline, not a voice agent.

## Known fast-follows (deliberately not in this PR)

- **CORS is not wired** — the web frontend's first cross-origin call will fail until
  `CORSMiddleware` is added in `app/main.py` (one line; permissive is fine for the demo).
- `/share/<unknown-id>` returns the JSON error shape, not an HTML 404 page.
- `og:image` is absent from the share page, so iMessage link previews are plain.
