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

## Guiding principles (Pragmatic Programmer)

- **Steel thread / tracer bullet:** get ONE voice working all the way through (record → backend → ElevenLabs → playback → share) before adding breadth. The thread proves the architecture end-to-end; everything else hangs off it. 
- **Orthogonality:** frontend, backend, and voice-config are decoupled behind a stable contract so the three of us never block each other.
- **Good-enough software:** ship the MVP. No gold-plating. Stretch goals only after the thread is green.
- **Prototype to learn:** the open ElevenLabs question gets answered by a 30-min spike, not by debate.

## The contract (lock this in hour 1 — it lets us parallelize)

`POST /convert`
- **in:** `audio` (any browser-native recording — webm/m4a/wav, ≤1 min, ≤10 MB), `voiceId`
- **out:** `{ url, title, audioUrl }`
- audio bytes live in object storage; the client fetches them via a **presigned URL** (the `audioUrl` in the response). 

`GET /share/:id` → page with title + audio player.

Once this contract is agreed, frontend can build against a mock and backend can build the real thing independently.

## Delivery principle — carry the audio, not a link

The magic is the recipient **playing the clip inline, in the thread, without opening a website**. So both surfaces ship the actual audio file by default; the share link is only a fallback.

- **iMessage extension:** `insertAttachment(audioFile)` → inline audio bubble (no app, no browser needed to play).
- **Web "Share" button:** `navigator.share({ files: [audioFile] })` → drops the same audio file straight into Messages via the iOS share sheet. No website to open.
- **Link = fallback only:** when `navigator.canShare({ files })` is false (Android, desktop, old browsers), share the `/share/:id` link instead so it still works everywhere.

## Roles

| person     | Domain                                      | Responsible for            |
| ---------- | ------------------------------------------- | -------------------------- |
| **john**   | Voices / pipeline + frontend support/design | Voices + cloning jobs      |
| **german** | Steel thread (backend + web)                | E2E thread on stock voices |
| **aaron**  | iMessage                                    | iMessage flow              |
|            |                                             |                            |


structure: 
- web app on github
- separate for ios? 

## Tech stack

Boring-and-fast choices, self-hosted on Aaron's Hetzner box (~75GB disk).

| Layer            | Choice                                    | Notes                                                                                            |
| ---------------- | ----------------------------------------- | ------------------------------------------------------------------------------------------------ |
| **Web frontend** | React (Vite + TS)                         | Recorder, voice picker, playback, share page.                                                    |
| **Backend**      | Python + **FastAPI**                      | `/convert` + `/share/:id`; calls ElevenLabs STS. *                                               |
| **iMessage**     | Swift + UIKit, **Messages framework**     | `MSMessagesAppViewController` extension; `AVAudioRecorder` records PCM `.wav` natively.          |
| **Metadata**     | **Postgres** (Docker)                     | `id → {title, audioUrl}`. Replaces the earlier Firestore lean now that we're self-hosting.       |
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
│      audioUrl}         │     │     (audioUrl = presigned)   │     │                         │
│         │              │     │                              │     │                         │
│  9. GET audioUrl ──────┼─────────────────────────────────────────►│ 10. stream MP3 bytes    │
│     (bytes) ◄──────────┼──────────────────────────────────────────┤                         │
│         ▼              │     │                              │     │                         │
│ 11. <audio> plays      │     │                              │     │                         │
└────────────────────────┘     └──────────────────────────────┘     └─────────────────────────┘
```

The server only ever returns **JSON metadata** (steps 7–8); the actual audio **bytes** travel client ↔ object storage directly (steps 9–10). ElevenLabs is the sole external dependency.

### Deploy flow (CI/CD)

Since SSH to the box already works, the fastest reliable path:
1. **Build:** GitHub Actions builds Docker images on push to `main`, pushes them to **GHCR** (GitHub Container Registry — free for the repo).
2. **Ship:** Action SSHes into Hetzner (store the private key as a repo secret) and runs `docker compose pull && docker compose up -d`.
3. **Serve:** Caddy out front terminates TLS + routes to the FastAPI and frontend containers.

For a 10-hour build, a one-line `appleboy/ssh-action` step that runs `docker compose pull && up -d` is plenty — no need for a registry at all if you'd rather `git pull` on the box and `docker compose up --build`. Start with the dumbest version; add GHCR only if build-on-server gets slow.

## Timeline (10 hours)

| Phase                       | ~Time | Goal                                                                                                                                                                                                               | Owner(s)     |
| --------------------------- | ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------ |
| **0 — Align + launch jobs** | 0–1h | Lock the contract. Group-pick the ~12 candidate voice types. **john fires the first cloning jobs immediately** (~6h turnaround — the critical path). | all |
| **1 — Steel thread** | 1–2h | german + aaron hardcode 1 stock voice: record → backend → STS → play back one clip. **DoD: one round-trip works.** Then backend is finalized + pushed, and they split into web + iOS. | german/aaron |
| **2 — Backend + storage** | 2–4h | Real `/convert`, validation (≤1 min / ≤10 MB), Postgres store for clips, MinIO presigned URLs, `/share/:id` page. | german |
| **3 — Web frontend** | 3–6h | Recorder UI, voice picker, playback, share page, **Share** button (file-first). | john/german |
| **4 — iMessage** | 3–6h | iMessage record/send/loading against the same `/convert`; insert the audio file inline. | aaron |
| **5 — Voice pipeline (background)** | 0h start → ~6h land | Source single-speaker data, fire cloning jobs in hour 0, tune params; hand voices over as they finish. | john |
| **6 — Converge + polish** | 6–9h | Swap custom voices in, narrow ~12 → best 6, error states, real infra. | all |
| **7 — Demo prep** | 9–10h | Lock the demo, dry run. | all |

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

**john — voice pipeline (critical path):** 

- gather single-speaker source data per candidate
- principles on
- fire off the cloning/training jobs immediately. can take up to 6 hours to return. 
- once finishes, help german with 

- **german
	- steel thread E2E:** record → backend → STS → playback → share, end to end, on **stock ElevenLabs voices** so it has zero dependency on john's jobs. Thread goes green long before custom voices exist.
- **aaron 
	- iMessage experience:** get an iMessage flow working (record, send, loading), after german has the backend up. (Pairs with german on the steel thread first.) 

**Convergence (~6h in):** trained voices come back → swap them into the already-working thread (low risk — pipeline proven on stock voices). Then narrow the ~12 down to the best **6** to ship. 


## Scope & limitations 

- **Ship 6 voices** — experiment with ~12 candidates, ship the best 6.
- **≤ 1 minute** per voice message.
- **≤ 10 MB** per upload — safety cap only; real clips are tiny (compressed upload ~150 KB, stored ElevenLabs output **~1 MB/min**).
	- **TTL: none for now.** At ~1 MB/clip the 75 GB box holds ~75k clips — no expiry needed for the demo; revisit if it ever grows.
- **Input format:** any browser-native recording (webm/opus, mp4/aac, or wav); normalized server-side to one canonical format via ffmpeg.
- Speech-to-speech only (not text-to-speech)

## Pieces of work

1. **Voice pipeline (john):** single-speaker source data per candidate → cloning/training jobs (~6h) → finished custom voices + tuned STS params.
2. **Backend server (german):** takes any native recording, normalizes via ffmpeg, calls ElevenLabs STS (→ MP3), stores the MP3 in object storage, and returns **JSON** `{url, title, audioUrl}` — the client fetches the audio from storage via the presigned `audioUrl`. **Postgres store** for share clips (`id → {title, audioUrl}`); `/share/:id` page.
3. **Web frontend (john/german):** record, pick voice, play, share — incl. a **Share** button (`navigator.share({ files })`) that sends the **audio file** into Messages (link fallback when file-share is unsupported).
4. **iMessage experience (aaron):** standalone iMessage app (`MSMessagesAppViewController`) — record in-keyboard, POST to the same `/convert`, fetch the MP3 from storage, loading state, then insert the **audio file** into the chat so it plays inline (link only as fallback). Apple signing/provisioning set up in hour 0–1; tested on a real device. Now a core track, not a stretch. (See *iMessage extension & sharing*.)

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

Separate pipeline, **same `/convert` contract** — no backend changes. Two ways a clip reaches a chat:

- **A. Share from the web page (build first, universal):** a **Share** button → `navigator.share({ files: [audioFile] })` opens the iOS share sheet → pick Messages → the **audio file** drops into the thread and plays inline. Falls back to sharing the `/share/:id` **link** when `navigator.canShare({ files })` is false. No Apple signing; this is the reliable baseline.
- **B. Native iMessage app (the delightful version):** standalone iMessage app (`MSMessagesAppViewController`, Swift + UIKit) in the keyboard — **record** via `AVAudioRecorder`, **POST** to `/convert`, fetch the MP3 from storage, show a loading state, then **insert the audio file** (`conversation.insertAttachment(...)`) so it plays inline in the chat.

**Ships the file, not the link** — the audio is inserted into the chat so it plays inline (no app, no browser to open). The share link is only a fallback when file-sharing isn't supported (Android, desktop, old browsers).

**Time risk:** needs an Apple Developer account + App ID + provisioning profile, and real send-in-Messages only tests on a **physical device / TestFlight** (simulator is fine for dev). Set this up in hour 0–1, in parallel — it's the main schedule hazard.

**Decoupling:** Path A is a button on German's share page; Path B is Aaron's standalone track. Both depend only on the frozen `/convert` + `/share/:id` contract, so neither blocks the steel thread.
