# voiceMix Web Recorder (Design)

**Date:** 2026-06-06 · **Owner:** German · **Status:** Approved (user fast-tracked to build)

## Goal
Press record on the site → mic audio runs the whole existing pipeline (normalize → engine →
MP3 → share). Full Stage-2 surface: recorder, voice picker, playback, file-first share.

## Decisions
- **Static page served by FastAPI at `GET /`** — vanilla HTML/JS, no React/Vite, no CORS, no
  new deploy (ships in the backend image Aaron's pipeline already rebuilds).
  **⚠️ Deviates from plan.md ("React Vite+TS in frontend/") — ping John before Stage-2 frontend work.**
- **Flow A — record first:** one big mic button; after stop, the voice grid appears; tapping a
  voice converts THAT take (tap another voice → re-convert same take; results cached per voice).
- 60s client-side auto-stop (server still enforces); browser-native format, server normalizes.
- Share: `navigator.share({files:[mp3]})` when supported, else copy `/share/:id` link + toast.
- `acceptsText` voices still take audio in this version (typed-text input out of scope).
- Errors: backend's `{"error": msg}` shown as toast; mic-denied gets a friendly inline message.

## Files
- `backend/app/templates/index.html` — page (Jinja template, dark theme like share.html)
- `backend/app/static/recorder.js` — MediaRecorder + API calls (`/static` mount in main.py)
- `backend/app/routes.py` — `GET /` renders index.html
- `backend/tests/test_index.py` — route renders, references recorder.js; static JS served

## Testing
Route/template/static via pytest; mic/JS behavior via manual browser pass against the live
server (mic APIs unavailable in pytest).

## Resolution (same day)

The team scaffolded the plan.md React SPA in `frontend/` (PRs #5–#8) in parallel. Decision:
**the SPA is the product/demo UI; this static page is the backend's dev console** — a
zero-dependency surface for exercising the pipeline. Both consume the same API (SPA
cross-origin via CORS, dev console same-origin).
