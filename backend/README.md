# voiceMix backend

FastAPI service: `/convert` (ElevenLabs STT→TTS), `/impersonate` (stub → John's Modal engine),
`/voices`, `/share/:id`, static `/audio/*`. Spec: `../docs/superpowers/specs/2026-06-06-backend-two-endpoints-design.md`.

**Frontends:** the React SPA in `../frontend/` (voicemix.awill.co) is the product/demo UI.
The recorder page this backend serves at `/` is a **dev console** — a zero-dependency way to
exercise the full pipeline (record → convert → share) without running the SPA.

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

- `/share/<unknown-id>` returns the JSON error shape, not an HTML 404 page.
- `og:image` is absent from the share page, so iMessage link previews are plain.
