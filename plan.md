# voiceMix — 10-Hour Build Plan

**Team:** Aaron, German, John 
**time:** 10 hours, end-to-end 
**Philosophy:** steel thread first, good-enough software, decouple so three people move in parallel.

## What we're building

a goofy tool that lets users record their voice, and send to friends with a different accent, character, etc. 
- i.e. "just drank a whole gallon of piss last night" in an old mans voice. 

```
record (native) ──> backend ──> ffmpeg ──> ElevenLabs STS ──> MP3 in object storage ──> shared as audio file
```

## Guiding principles

- **Steel thread / tracer bullet:** get ONE voice working all the way through (record → backend → ElevenLabs → playback → share) before adding breadth. The thread proves the architecture end-to-end; everything else hangs off it. 
- **Orthogonality:** frontend, backend, and voice-config are decoupled behind a stable contract so the three of us never block each other.

## The contract (lock this in hour 1 — it lets us parallelize)

`POST /convert`
- **in:** `audio` (any browser-native recording — webm/m4a/wav, ≤1 min, ≤10 MB), `voiceId`
- **out:** `{ url, title, audioUrl }`
- audio bytes live in object storage; the client fetches them via a **presigned URL** (the `audioUrl` in the response). The `audioUrl` is **minted fresh on every request** — we persist only the durable **object key**, never the expiring presigned URL (see Metadata note below).

`GET /share/:id` → page with title + audio player.

Once this contract is agreed, frontend can build against a mock and backend can build the real thing independently.

## carry the audio, not a link

The magic is the recipient **playing the clip inline, in a text thread, without opening a website**. So both surfaces ship the actual audio file by default; the share link is only a fallback.

- **iMessage extension:** `insertAttachment(audioFile)` → inline audio bubble (no app, no browser needed to play).
- **Web "Share" button:** `navigator.share({ files: [audioFile] })` → drops the same audio file straight into Messages via the iOS share sheet. No website to open.
- **Link = fallback only:** when `navigator.canShare({ files })` is false (mainly desktop browsers and old browsers), share the `/share/:id` link instead so it still works everywhere. Note: **Android Chrome supports file sharing** (Web Share API Level 2, since Chrome 75) — it takes the file path, not the fallback. On Android the file always sends; whether it renders inline depends on the receiving app (Google Messages/RCS, WhatsApp, etc.).
- IF TIME - we can give option when user clicks share to send link OR audio file. 


## Roles

| person     | Domain                                      | Responsible for            |
| ---------- | ------------------------------------------- | -------------------------- |
| **john**   | Voices / pipeline + frontend support/design | Voices + cloning jobs      |
| **german** | Steel thread (backend + web)                | E2E thread on stock voices |
| **aaron**  | iMessage                                    | iMessage flow              |
|            |                                             |                            |

structure: 
- fullstack web app on github
- separate ios repo

## Tech stack

Boring-and-fast choices, self-hosted on Aaron's Hetzner box (~75GB disk).

| Layer            | Choice                                    | Notes                                                                                            |
| ---------------- | ----------------------------------------- | ------------------------------------------------------------------------------------------------ |
| **Web frontend** | React (Vite + TS)                         | Recorder, voice picker, playback, share page.                                                    |
| **Backend**      | Python + **FastAPI**                      | `/convert` + `/share/:id`; calls ElevenLabs STS. *                                               |
| **iMessage**     | Swift + UIKit, **Messages framework**     | `MSMessagesAppViewController` extension; `AVAudioRecorder` records PCM `.wav` natively.          |
| **Metadata**     | **Postgres** (Docker)                     | `id → {title, objectKey, contentType, createdAt}`. **Store the durable object key, not a presigned URL** — presigned URLs expire, so persisting one would silently break `/share/:id` later (contradicts "TTL: none"). The backend mints a fresh `audioUrl` from the object key on each `/convert` and `/share/:id` request. Replaces the earlier Firestore lean now that we're self-hosting. |
| **Object store** | **MinIO** (S3-compatible, Docker)         | Stores the **MP3** clips; native **presigned URLs** satisfy the contract's fetch-by-URL flow.    |
| **Deploy**       | **Docker Compose** on Hetzner + **Caddy** | Caddy = automatic HTTPS (mic `getUserMedia` needs a secure origin). GitHub Actions → SSH deploy. |

**Watch-outs:**
- **Single S3 contract:** FastAPI talks to MinIO with the standard S3 SDK (`boto3`), so swapping MinIO → real S3 later is a config change, not a rewrite.

### Audio format

No single upload format — formats the browser records in differ depending on what its device/OS/browser support, and the **server normalizes** to one canonical format with **ffmpeg**.  see flow below: 

**Flow:**

```
┌────────────────────────┐     ┌──────────────────────────────┐     ┌─────────────────────────┐
│ CLIENT                 │     │ HETZNER SERVER (FastAPI)     │     │ HETZNER OBJECT STORAGE  │
│ browser / iMessage     │     │                              │     │ MinIO                   │
├────────────────────────┤     ├──────────────────────────────┤     ├─────────────────────────┤
│ 1. record native       │     │                              │     │                         │
│    webm / m4a / wav     │     │                              │     │                         │
│         │              │     │                              │     │                         │
│  2. POST /convert ─────┼────►│ 3. ffmpeg → WAV 16kHz mono   │     │                         │
│     (bytes)            │     │         │                    │     │                         │
│                        │     │         ▼                    │     │                         │
│                        │     │  4. ElevenLabs STS ──► MP3   │     │                         │
│                        │     │     (external API call)      │     │                         │
│                        │     │         │                    │     │                         │
│                        │     │  5. save MP3 ────────────────┼────►│ 6. store clip           │
│                        │     │         │                    │     │                         │
│  8. receive JSON ◄─────┼─────┤  7. return JSON              │     │                         │
│     {url,title,        │     │     {url, title, audioUrl}   │     │                         │
│      audioUrl}         │     │  (audioUrl = freshly minted  │     │                         │
│                        │     │   presigned; DB stores key)  │     │                         │
│         │              │     │                              │     │                         │
│  9. GET audioUrl ──────┼─────────────────────────────────────────►│ 10. stream MP3 bytes    │
│     (bytes) ◄──────────┼──────────────────────────────────────────┤                         │
│         ▼              │     │                              │     │                         │
│ 11. <audio> plays      │     │                              │     │                         │
└────────────────────────┘     └──────────────────────────────┘     └─────────────────────────┘
```

The server only ever returns **JSON metadata** (steps 7–8); the actual audio **bytes** travel client ↔ object storage directly (steps 9–10). ElevenLabs is the sole external dependency.

## Scope & limitations

- **Ship 6 voices** — experiment with ~12 candidates, ship the best 6.
- **≤ 1 minute** per voice message.
- **≤ 10 MB** per upload — safety cap only; real clips are tiny (compressed upload ~150 KB, stored ElevenLabs output **~1 MB/min**).
	- **no TTL for now.** At ~1 MB/clip the 75 GB box holds ~75k clips — no expiry needed for the demo; revisit if it ever grows.
- **Input format:** any browser-native recording (webm/opus, mp4/aac, or wav); normalized server-side to one canonical format via ffmpeg.
- Speech-to-speech only (not text-to-speech)

## Timeline (10 hours)

| Phase                       | ~Time              | Goal                                                                                                                                                                   | Owner(s)     |
| --------------------------- | ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------ |
| **0 — Align + launch jobs** | 0–1h               | Lock the contract. Group-pick the ~12 candidate voice types. **john fires the first cloning jobs immediately** (~6h turnaround — the critical path).                   | all          |
| **1 — Voice pipeline**      | 0h start → ~6h lan | Source single-speaker data, fire cloning jobs in hour 0, tune params; hand voices over as they finish.                                                                 | john         |
| **1 — Steel thread**        | 1–2h               | hardcode 1 stock voice: record → backend → STS → play back one clip. **DoD: one round-trip works.** Then backend is finalized + pushed, and they split into web + iOS. | german/aaron |
| **2 — Backend + storage**   | 2–4h               | Real `/convert`, validation (≤1 min / ≤10 MB), Postgres store for clips, MinIO presigned URLs, `/share/:id` page.                                                      | german       |
| **2 — Web frontend**        | 3–6h               | Recorder UI, voice picker, playback, share page, **Share** button (file-first).                                                                                        | john/german  |
| **2 — iMessage**            | 3–6h               | iMessage record/send/loading against the same `/convert`; insert the audio file inline.                                                                                | aaron        |
| **3 — Converge + polish**   | 6–9h               | Swap custom voices in, narrow ~12 → best 6, error states, real infra.                                                                                                  | all          |
| **4 — Demo prep**           | 9–10h              | Lock the demo, dry run.                                                                                                                                                | all          |


## Plan (stages)

### Stage 0 — group (everyone):
- brainstorm and lock a shortlist of **~12 candidate voice types** to experiment with: 
	- female
	- male
	- baby
	- jfk/mlk/etc
	- etc

### Stage 1

split into parallel tracks.

**john — voice pipeline :** 

- gather single-speaker source data per candidate
- principles on
- fire off the cloning/training jobs immediately. can take up to 6 hours to return. 
- once finishes, help german with 

**german**
- steel thread E2E:** record → backend → STS → playback → share, end to end, on **stock ElevenLabs voices** so it has zero dependency on john's jobs. Thread goes green long before custom voices exist.

**aaron**
- iMessage experience:** get an iMessage flow working (record, send, loading), after german has the backend up. (Pairs with german on the steel thread first.) 

### Stage 2:  Backend + storage & frontend fixes

german works on real backend endpoints, object storage, links, sending audio file when you click share. 

aaron does ios fe

john does web fe(if hes done with voice pipeline)
### Stage 3: converence + polish

**Convergence (~6h in):** trained voices come back → swap them into the already-working thread (low risk — pipeline proven on stock voices). Then narrow the ~12 down to the best **6** to ship. 

### Stagfe 4: demo prep

prep for our winning speeches. 


## Open questions

1. **Does ElevenLabs handle multiple speakers compressed into one voice well?**
	- **Answered: No — use one clean speaker per voice.** ElevenLabs cloning (Instant *and* Professional) is built around a *single, consistent speaker*. Per their docs, more than one speaker (or noise) "confuses the AI" so it can't discern which voice to clone, and the clone reproduces *everything* it hears — artifacts, reverb, other speakers included — producing a muddy/unstable result. 

## TODO

- [ ] **Stage 0: group-pick ~12 candidate voices**; narrow to the best 6 after experiments.
- [ ] Lock the `/convert` + `/share` contract (hour 0).
- [x] Assign roles — john = voices/pipeline, german = steel thread, aaron = iMessage.
- [ ] Get ElevenLabs API key + confirm STS **and cloning** endpoints & params.
- [x] Answer the multi-speaker spike question. → No; one clean speaker per voice (see Open Questions).
- [x] **Pick store + hosting** → Postgres + MinIO, self-hosted on Hetzner via Docker Compose (see Tech stack).
- [x] Pick web stack → React (Vite + TS); backend FastAPI (tentative, German to confirm).
- [ ] **Confirm the critical path:** john fires the first cloning jobs in hour 0 (~6h turnaround).
- [ ] Define "demo done" — what we show at hour 10.

## Appendix


**iMessage extension & sharing (aaron)**

testflight build submitted friday night, just blank shell so we arent blocked tmw. regardless can still demo locally. 

Separate pipeline, **same `/convert` contract** — no backend changes. Two ways a clip reaches a chat:

- **A. Share from the web page (build first, universal):** a **Share** button → `navigator.share({ files: [audioFile] })` opens the iOS share sheet → pick Messages → the **audio file** drops into the thread and plays inline. Falls back to sharing the `/share/:id` **link** when `navigator.canShare({ files })` is false. No Apple signing; this is the reliable baseline.
- **B. Native iMessage app (the delightful version):** standalone iMessage app (`MSMessagesAppViewController`, Swift + UIKit) in the keyboard — **record** via `AVAudioRecorder`, **POST** to `/convert`, fetch the MP3 from storage, show a loading state, then **insert the audio file** (`conversation.insertAttachment(...)`) so it plays inline in the chat.

### Deploy flow (CI/CD)

**Decision: GitHub Actions SSH-deploy, build-on-box, no registry.** The point isn't just automation — it's **shared deploy access**. Tying deploys to a person + their SSH creds makes that person a bottleneck and a single point of failure during the crunch. CI decouples deploy from any individual: anyone who can merge to `main` ships, and the box's deploy key lives as a GitHub secret so nobody needs personal SSH access.

Path (push to `main`):
1. **Ship:** a single `appleboy/ssh-action` step SSHes into Hetzner (deploy private key stored as a repo secret) and runs `git pull && docker compose up -d --build` on the box.
2. **Serve:** Caddy out front terminates TLS + routes to the FastAPI and frontend containers.

**No GHCR / no image registry** — we build on the box (`docker compose up --build`). The registry is the "heavy" part of CI/CD and buys us nothing for a 10-hour build; add it later only if build-on-server gets slow.

**Backup access (do this in hour 0):** add German's + John's SSH public keys to the box as an escape hatch, so a CI hiccup during the crunch doesn't block deploys.

**Caveat:** push-to-`main` auto-deploys, so a bad merge ships immediately — fine for a hackathon, just be aware. Needs setting up in hour 0: teammate GitHub repo access + the deploy secret + the `main`-push trigger.
