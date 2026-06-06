# voiceMix — 10-Hour Build Plan

**Team:** Aaron, German, John 

**time:** 10 hours, end-to-end 

**Philosophy:** steel thread first, good-enough software, decouple so three people move in parallel.

## What we're building

a goofy tool that lets users record their voice, and send to friends with a different accent, character, etc. 
- i.e. "just drank a whole gallon of piss last night" in an old mans voice. 

```
record (native) ──> backend ──> ffmpeg ──> ElevenLabs STS ──> MP3 on disk (Docker volume) ──> shared as audio file
```

## Guiding principles

- **Steel thread / tracer bullet:** get ONE voice working all the way through (record → backend → ElevenLabs → playback → share) before adding breadth. The thread proves the architecture end-to-end; everything else hangs off it. 
- **Orthogonality:** frontend, backend, and voice-config are decoupled behind a stable contract so the three of us never block each other.

## The contract (lock this in hour 1 — it lets us parallelize)

**Two convert endpoints, same response shape** — frontend/iMessage treat them interchangeably and pick by which voice the user chose. (Endpoint names are a suggestion; lock in hour 1.)

Each voice in the picker catalog carries an **`engine`** field (`"elevenlabs"` → `/convert`, `"modal"` → `/impersonate`) so the client routes to the right endpoint automatically. The picker also flags which voices accept **text input** (path B only).

`POST /convert` — **speech-to-speech** (path A: generic voices via ElevenLabs)
- **in:** `audio` (any browser-native recording — webm/m4a/wav, ≤1 min, ≤10 MB), `voiceId`
- **out:** `{ url, title, audioUrl }`
- Genuinely STS — needs your audio; keeps the **sender's** delivery, swaps timbre. This is the steel thread.

`POST /impersonate` — **ASR→TTS** (path B: celebrity/impression voices via Whisper + CosyVoice2/GPT-SoVITS on Modal)
- **in:** `voiceId` + **EITHER** `audio` (transcribed server-side via Whisper, same ≤1 min / ≤10 MB caps) **OR** `text` (skip transcription).
- **out:** `{ url, title, audioUrl }`
- **Not forced to be STS:** internally it transcribes to text then synthesizes, so it accepts text directly. Audio input keeps the unified "record" UX; text input is a free option (no Whisper step → no transcription errors, lower latency). Regenerates the words in the **target's** full delivery (accent + cadence); the sender's own delivery is discarded.

**Both endpoints:** audio bytes are written to an **on-disk Docker volume** on the box and **served by the backend itself**; the `audioUrl` in the response points at a backend route (e.g. `/clips/:id`). We persist the durable **clip id / filename** in SQLite, not a URL — so the link never expires (see Metadata note below).

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
| **Metadata**     | **SQLite** (file on the Docker volume)    | `id → {title, filename, contentType, createdAt}`. Stores the durable **clip id / filename**, never a URL. The backend builds `audioUrl` as its own route (`/clips/:id`) and streams the file. SQLite (not Postgres) — at this scale a single file on disk is plenty, and it's one fewer service to run. |
| **Object store** | **On-disk Docker volume** (`/data`)       | Stores the **MP3** clips on the box's disk; the backend serves them directly. Dropped MinIO — no object store, no presigned URLs, fewer moving parts under the time budget. |
| **Deploy**       | **Docker Compose** on Hetzner + **Caddy** | Caddy = automatic HTTPS (mic `getUserMedia` needs a secure origin). GitHub Actions **builds the image, pushes to GHCR, box pulls** (see Deploy flow). |

**Watch-outs:**
- **One disk = one box:** clips live on the box's local volume, so there's no second machine to fail — but also no replication. Fine for the demo (~1 MB/clip, 75 GB box). If we ever need durability/scale, the backend's storage layer can swap to S3 behind the same `audioUrl` contract.

### Audio format

No single upload format — formats the browser records in differ depending on what its device/OS/browser support, and the **server normalizes** to one canonical format with **ffmpeg**.  see flow below: 

**Flow:**

```
┌────────────────────────┐     ┌──────────────────────────────────────────────────┐
│ CLIENT                 │     │ HETZNER SERVER (FastAPI)                          │
│ browser / iMessage     │     │   + on-disk volume (MP3 clips) + SQLite (meta)    │
├────────────────────────┤     ├──────────────────────────────────────────────────┤
│ 1. record native       │     │                                                  │
│    webm / m4a / wav     │     │                                                  │
│         │              │     │                                                  │
│  2. POST /convert ─────┼────►│ 3. ffmpeg → WAV 16kHz mono                       │
│     (bytes)            │     │         │                                        │
│                        │     │         ▼                                        │
│                        │     │  4. ElevenLabs STS ──► MP3 (external API call)   │
│                        │     │         │                                        │
│                        │     │  5. write MP3 → /data volume; row → SQLite       │
│                        │     │         │                                        │
│  8. receive JSON ◄─────┼─────┤  7. return JSON {url, title, audioUrl}           │
│     {url,title,        │     │     (audioUrl = backend route /clips/:id)        │
│      audioUrl}         │     │                                                  │
│         │              │     │                                                  │
│  9. GET audioUrl ──────┼────►│ 10. backend streams MP3 bytes from /data volume  │
│     (bytes) ◄──────────┼─────┤                                                  │
│         ▼              │     │                                                  │
│ 11. <audio> plays      │     │                                                  │
└────────────────────────┘     └──────────────────────────────────────────────────┘
```

The server returns **JSON metadata** (steps 7–8), then **streams the audio bytes itself** from the on-disk volume on the follow-up `GET audioUrl` (steps 9–10) — no separate object store, no presigned URLs. ElevenLabs is the sole external dependency for the steel thread (path A below); the optional celebrity path adds Modal — see Voice engines.

## Voice engines (two paths, one `/convert` contract)

**Two endpoints** — `POST /convert` (STS) and `POST /impersonate` (ASR→TTS) — **same JSON response**, so frontend/iMessage pick by the chosen voice and don't care which engine ran. Split endpoints also keep the orthogonality clean: german owns `/convert` (ElevenLabs), john owns `/impersonate` (Modal).

**A. Generic voices (accents, ages, genders) — ElevenLabs. The reliable spine.** Stock voices + **Instant Voice Cloning (IVC)** on found single-speaker recordings (no identity gate — found audio is fine for non-famous voices). Speech-to-speech: keeps the *sender's* delivery, swaps timbre. Zero infra — this is the steel thread.

**B. Celebrity / impression voices (JFK, etc.) — open-source ASR→TTS on Modal. john's investigation track.** Whisper (ASR) → **CosyVoice2** *or* **GPT-SoVITS** (few-shot TTS) on Modal (serverless GPU, scales to zero). Regenerates the words in the target's *full* delivery — accent + cadence, not just timbre. The only route to convincing dead-celebrity voices.

**Why not ElevenLabs PVC for celebrities?** PVC is **identity-locked**: it requires a live voice-match captcha — you record yourself reading a prompt, and it's compared against the uploaded samples to confirm same speaker. You can't produce a live JFK, so found audio can't pass. PVC only works for a voice you can record on demand (i.e. one of us). **This kills the earlier "~6h PVC cloning" critical path:** generic voices are instant IVC, celebrities go open-source — no 6h job blocks us.

**Two behaviors, on purpose:** path A keeps your delivery (you, old-man-voiced); path B regenerates in the celebrity's delivery (JFK reads your text). Same UI, slightly different feel — fine, just know it going in.

**Latency (path B, Modal):** ~4–8s warm for a short clip (Whisper ~1s + TTS ~3–5s); cold start 15–45s → use `keep_warm` for the demo. The async loading state already covers this. CosyVoice2 streaming (~150ms first packet) is the lever if perceived latency bites.

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
| **0 — Align + launch jobs** | 0–1h               | Lock the contract. Group-pick the ~12 candidate voice types. **john starts generic IVC clones + fires the path-B open-source spike on Modal** (clone one celebrity, gut-check quality + latency).                   | all          |
| **1 — Voice pipeline**      | 0h start → ongoing | Generic: source clean single-speaker data → IVC. Celebrity: spike open-source ASR→TTS on Modal (CosyVoice2/GPT-SoVITS), confirm quality+latency; hand voices over as they land. | john         |
| **1 — Steel thread**        | 1–2h               | hardcode 1 stock voice: record → backend → STS → play back one clip. **DoD: one round-trip works.** Then backend is finalized + pushed, and they split into web + iOS. | german/aaron |
| **2 — Backend + storage**   | 2–4h               | Real `/convert`, validation (≤1 min / ≤10 MB), write clips to the `/data` volume + SQLite metadata, backend serves `audioUrl`, `/share/:id` page.                       | german       |
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

- **celebrity / impression voices (path B):** spike the **open-source ASR→TTS** route on Modal — Whisper → **CosyVoice2 or GPT-SoVITS**. Clone ONE celebrity early (hr 1–2), confirm quality clears the demo bar **and** measure real cold/warm latency before committing. Fall back to IVC celebrity (lower fidelity, sender's delivery) if it doesn't clear the bar.
- once voices land, help german with the thread.

**german**

- **generic voices (path A):** source clean, single-speaker recordings per accent/age/gender → ElevenLabs **IVC** (instant, found audio OK). One clean sample per voice, not hours.
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
- [x] **Pick store + hosting** → on-disk Docker volume for clips + SQLite for metadata, self-hosted on Hetzner via Docker Compose (dropped MinIO/Postgres — see Tech stack).
- [x] Pick web stack → React (Vite + TS); backend FastAPI (tentative, German to confirm).
- [ ] **john: open-source celebrity-voice spike** — Whisper + **CosyVoice2 or GPT-SoVITS** on Modal; clone one celebrity early (hr 1–2), confirm quality clears the demo bar **and** measure cold/warm latency before committing (see Voice engines). Fall back to IVC celebrity if it doesn't.
- [ ] **Confirm the critical path:** generic voices = instant IVC (no 6h job); celebrity path-B is parallel + gated by the spike, so it can't sink the thread.
- [ ] Define "demo done" — what we show at hour 10.

## Appendix


**iMessage extension & sharing (aaron)**

testflight build submitted friday night, just blank shell so we arent blocked tmw. regardless can still demo locally. 

Separate pipeline, **same `/convert` contract** — no backend changes. Two ways a clip reaches a chat:

- **A. Share from the web page (build first, universal):** a **Share** button → `navigator.share({ files: [audioFile] })` opens the iOS share sheet → pick Messages → the **audio file** drops into the thread and plays inline. Falls back to sharing the `/share/:id` **link** when `navigator.canShare({ files })` is false. No Apple signing; this is the reliable baseline.
- **B. Native iMessage app (the delightful version):** standalone iMessage app (`MSMessagesAppViewController`, Swift + UIKit) in the keyboard — **record** via `AVAudioRecorder`, **POST** to `/convert`, fetch the MP3 from storage, show a loading state, then **insert the audio file** (`conversation.insertAttachment(...)`) so it plays inline in the chat.

### Deploy flow (CI/CD)

**Decision: GitHub Actions — build image in CI, push to GHCR, box pulls.** The point isn't just automation — it's **shared deploy access**. Tying deploys to a person + their SSH creds makes that person a bottleneck and a single point of failure during the crunch. CI decouples deploy from any individual: anyone who can merge to `main` ships, and the box's deploy key lives as a GitHub secret so nobody needs personal SSH access.

**This is PIPE 1 — backend/server only.** Frontend deploys on its own pipeline.

Path (push to `main`, paths `backend/**` or `deploy/**`):
1. **Build:** GitHub Actions builds the `backend/` image and pushes it to **GHCR** (`ghcr.io/aaronw122/voicemix-backend`), tagged `:latest` + `:sha-<commit>`.
2. **Deploy:** `appleboy/scp-action` copies the compose + Caddyfile to the box, then `appleboy/ssh-action` SSHes in (deploy key + GHCR creds as repo secrets) and runs `docker compose pull && up` — pinned to the commit's **SHA tag**. The box only pulls prebuilt images; **it never compiles.**
3. **Verify:** a post-deploy **health gate** curls `/health` on the box; the deploy fails (with container logs) if the backend doesn't come up healthy.
4. **Serve:** Caddy out front terminates TLS + reverse-proxies the FastAPI backend. (Public access will move to a **Cloudflare Tunnel** — then Cloudflare terminates TLS at the edge and Caddy can be simplified or dropped.)

**Why build-in-CI over build-on-box:** the box stays clean (no source, no toolchain, no compile load during a deploy), every environment runs the identical image, and the SHA tag gives free rollback. GHCR is ~15 lines now — the old "registry is heavy" reasoning no longer holds.

**Hardening already in place (from a tribunal review):** SHA-pinned deploys, post-deploy health gate, single-deploy `concurrency` guard, backend bound to `127.0.0.1` (not public). MinIO/Postgres were dropped entirely, which also removed a public admin-console exposure.

**Backup access (do this in hour 0):** add German's + John's SSH public keys to the box as an escape hatch, so a CI hiccup during the crunch doesn't block deploys.

**Caveat:** push-to-`main` auto-deploys, so a bad merge ships immediately — fine for a hackathon, just be aware. Setup needed in hour 0: teammate GitHub repo access; repo secrets (`HETZNER_HOST`/`USER`/`SSH_KEY`, `GHCR_USERNAME`/`GHCR_TOKEN`); the box prepped (Docker + `~/voicemix/.env`).
