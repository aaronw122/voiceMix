# Tribunal Review — `plan.md`

## Role 1 — Investigator

### 1. The `/convert` contract is too thin to truly parallelize

The plan says the contract should be "locked" in hour 1 and will let frontend and backend move independently (lines 23-32), but the shape only defines `audio`, `voiceId`, and `{ url, title, audioUrl }` (lines 25-28). That is not enough for independent implementation.

Missing contract details:
- Multipart field names and content type: is `audio` a `multipart/form-data` file field, raw request body, or base64 JSON?
- File metadata: original filename, MIME type, duration, size, extension.
- Response IDs: `/share/:id` exists (line 30), but the `POST /convert` response does not explicitly include `id`; `url` probably implies the share URL, but it is ambiguous.
- Error shape: no standard `{ code, message }`, retryability, validation failures, ElevenLabs failures, ffmpeg failures, or rate-limit failures.
- Processing model: synchronous conversion is implied, but not stated. STS latency may be long enough that the UI needs progress, timeout handling, or async job polling.
- Voice list contract: frontend needs `voiceId`, display name, availability, and whether a voice is stock/custom. The plan says voice-config is decoupled (line 19), but no `/voices` or static config shape is defined.

This is load-bearing because the web, backend, and iMessage tracks all depend on the same assumptions. If those assumptions diverge, the teams will integrate late and painfully.

### 2. Presigned `audioUrl` is a bad persisted metadata field

The plan says Postgres stores `id -> {title, audioUrl}` (line 65), and the contract returns `audioUrl` as a presigned URL (lines 27-28, 94-96). Presigned URLs expire. Storing one as durable metadata conflicts with `/share/:id`, which must work later (line 30), and with "TTL: none for now" (line 112).

The durable record should store an object key, content type, title, created time, and maybe duration. The backend should generate a fresh presigned URL when returning `/convert` or rendering `/share/:id`, or proxy the object through the backend/Caddy. Otherwise share pages will silently break after URL expiry.

### 3. "Server only ever returns JSON" conflicts with file-first sharing

The audio flow says the server only returns JSON and bytes travel directly between client and object storage (line 105). But the delivery principle requires both web and iMessage to share the actual audio file (lines 36-40, 197-200). That means clients must fetch the `audioUrl` as a Blob/File before sharing or inserting. The plan mentions this in the appendix for iMessage (line 198), but not in the main contract or web flow.

This matters because web file sharing requires a `File` object with a MIME type and filename. iMessage `insertAttachment` requires a local file URL, so the iMessage extension needs download-to-temp-file behavior, file extension correctness, and cleanup.

### 4. iMessage assumptions are optimistic and probably the largest schedule risk

The plan treats `insertAttachment(audioFile) -> inline audio bubble` as a core delivery guarantee (line 38) and schedules iMessage for hours 3-6 (line 125). The appendix correctly notes Apple Developer account, App ID, provisioning profile, and real device/TestFlight testing risk (line 202), but the timeline does not protect that risk enough.

Specific hazards:
- A Messages extension is not the same as a standalone iOS app; extension lifecycle, sandboxing, UI constraints, and file access are different.
- `MSConversation.insertAttachment` can attach a local file, but whether it renders as an inline playable audio bubble depends on file type, UTI/MIME, recipient device, Messages behavior, and testing on real hardware.
- Recording inside a Messages extension may need microphone permission flow and Info.plist entries; permission prompts inside extensions can be awkward.
- TestFlight/App Store distribution for an iMessage app is not a 10-hour dependency to discover late. Direct device install from Xcode may be enough for demo, but that needs to be explicitly the demo path.

If the demo depends on native iMessage working, this can sink the build. If web share is the baseline and native iMessage is stretch, the plan is much safer.

### 5. Web Share API details are overstated

The plan says the web share button "drops the same audio file straight into Messages via the iOS share sheet" (line 39), and that Android Chrome supports file sharing since Chrome 75 (line 40). The direction is right, but the guarantee is stronger than reality.

Risks:
- Web Share with files only works in secure contexts and is browser/platform dependent.
- `navigator.canShare({ files })` can fail based on file type, file size, browser, and user agent.
- Safari/iOS behavior around sharing Blob-created `File` objects can be finicky; filename and MIME type matter.
- "Android Chrome supports file sharing" does not mean every target app will accept/play MP3 inline, which the plan acknowledges partly (line 40).

For the demo, file-first web share is a reasonable baseline, but it should be validated on the exact target phone/browser early.

### 6. ElevenLabs cloning is treated as a 6-hour deterministic job, but the plan has no fallback

The plan identifies cloning jobs as the critical path with an assumed ~6-hour turnaround (lines 120-121, 148, 166, 187). It also says the steel thread uses stock voices to avoid dependency on John's jobs (line 152), which is good. But the product scope still says "Ship 6 voices" after experimenting with ~12 candidates (line 109), and convergence assumes trained voices come back around hour 6 (line 166).

Missing fallback:
- If custom voices are delayed, bad, quota-limited, rejected, or require more source material, ship stock/community/library voices.
- If only 2-3 custom voices work, scope should allow mixing stock voices and custom voices.
- If cloning requires consent/rights confirmation or sufficient clean samples, "JFK/MLK/etc" candidates (line 137) are risky legally, ethically, and possibly platform-policy-wise.

The plan should state that the demo is complete with stock STS voices, and custom clones are an enhancement.

### 7. The timeline underestimates infra and integration

The timeline assigns the real backend, validation, Postgres, MinIO, presigned URLs, and share page to hours 2-4 (line 123). It also expects web frontend from hours 3-6 (line 124), iMessage from hours 3-6 (line 125), real infra in hours 6-9 (line 126), and demo prep in hour 9-10 (line 127).

Hidden time sinks:
- Docker Compose wiring for FastAPI, ffmpeg, Postgres, MinIO, Caddy, env vars, buckets, CORS, TLS, and public URLs.
- GitHub Actions/SSH deployment and secrets (lines 208-215).
- MinIO public endpoint and presigned URL host correctness behind Caddy.
- ffmpeg install and codec support inside the container.
- Large upload limits through Caddy/FastAPI.
- Mobile browser microphone testing over HTTPS.
- Cross-origin audio playback and CORS from MinIO to frontend/share page.

For a 10-hour build, adding Postgres + MinIO + Caddy + CI/CD may be too much. A local-file or single-volume object store path may be faster for the demo, with MinIO added only if needed.

### 8. Security and abuse controls are underdefined

The app accepts user audio and calls a paid API, but the plan does not define auth, rate limiting, API key protection, origin restrictions, or abuse caps. Upload caps exist (lines 110-112), but they are not sufficient.

Minimum needed:
- Server-side duration validation after decoding, not just client-side.
- Rate limit by IP/session.
- Validate `voiceId` against an allowlist.
- Reject unsupported MIME/content after probing with ffmpeg/ffprobe.
- Ensure ElevenLabs API key never reaches clients.
- Avoid public write access to MinIO.

This is not necessarily fatal for a closed demo, but a public URL with an unauthenticated paid conversion endpoint can burn API quota quickly.

### 9. Audio validation is harder than stated

The plan accepts "any browser-native recording" (line 26) and normalizes via ffmpeg (lines 74, 86, 113). That is directionally right, but "any" is too broad. Browser recordings can be `webm/opus`, `audio/mp4`, `audio/aac`, `audio/wav`, or Safari-specific formats. Some ffmpeg builds may lack codecs depending on packaging.

The duration cap needs `ffprobe` after upload; file size alone does not prove duration. The iMessage side says `AVAudioRecorder` records PCM `.wav` natively (line 64), which can exceed the 10 MB cap near or above 1 minute depending on sample rate/bit depth/channels unless configured carefully.

### 10. `/share/:id` serving model is ambiguous

The contract says `GET /share/:id -> page with title + audio player` (line 30), while the tech stack says FastAPI owns `/share/:id` (line 63) and React owns playback/share page (line 62). It is unclear whether FastAPI server-renders the share page, proxies to Vite/static React, or the frontend route handles it and calls an API.

That matters for deployment routing in Caddy and for mocked frontend work. Decide early:
- API: `POST /api/convert`, `GET /api/clips/:id`
- Frontend route: `/share/:id`
- Object/audio endpoint: either presigned object URL or `/api/clips/:id/audio`

### 11. The role split contradicts itself

The roles table says German owns backend + web steel thread (lines 47, 122), John owns voices + frontend support/design (line 46), and Aaron owns iMessage (line 48). Later Stage 1 says Aaron pairs with German on the steel thread before iMessage (line 155), Stage 2 says German handles "sending audio file when you click share" (line 159), and John does web frontend only "if hes done with voice pipeline" (line 163).

This is workable socially, but not a clear parallelization plan. The web share flow may be orphaned if John is stuck on voices and German is deep in backend/infra.

### 12. The plan contains unresolved repo/product structure

Lines 52-54 literally ask whether web and iOS are separate. That is a setup decision, not a detail. If the iMessage code needs a separate Xcode project, shared config, endpoint constants, and assets, that should be decided in hour 0. A 10-hour build cannot afford repo-structure ambiguity once coding starts.

### 13. Demo definition is missing

The TODO explicitly says "Define demo done" is still open (line 188). That is a blocking product gap for a 10-hour plan. The team needs to know whether demo success is:
- Web record -> convert -> playback -> share file into Messages.
- Native iMessage record -> convert -> insert playable audio.
- Custom cloned voices required, or stock voices acceptable.
- Public deployed URL required, or local tunnel acceptable.

Without this, the team may optimize for different finish lines.

## Role 2 — Devil's Advocate

### Pushback on Investigator findings

The contract criticism is real, but it should not become a heavyweight API design exercise. For a hackathon-style build, a one-page concrete contract is enough: multipart field names, sync response, `id`, `shareUrl`, `audioUrl`, and a simple error shape. Do not spend an hour designing a job system unless the first STS spike proves conversion latency is too high.

The presigned URL issue is important, but not necessarily blocking for a 10-hour demo. If presigned URLs are set to 7 days and the demo happens today, storing `audioUrl` would work. Still, it is an easy architectural fix to store object keys instead, so there is little reason to keep the weaker design.

The "server only returns JSON" conflict is more of an implementation note than a plan flaw. Fetching the audio as a Blob/File is straightforward on web, and iOS can download the file. It needs to be written down because multiple clients need to do it, but it does not threaten the concept.

The iMessage risk is correctly identified, but it may be over-weighted if Path A, the web share sheet, is accepted as the reliable baseline (lines 197-198). The plan already calls native iMessage "the delightful version" and notes setup risk (line 202). The fix is to demote native iMessage from core demo path, not to remove it.

The Web Share critique can become pedantic. The plan acknowledges fallback links (lines 40 and 197), which is the right mitigation. The practical requirement is early device testing, not a different architecture.

The infra concern is partly overstated. FastAPI + Docker Compose + Caddy + MinIO can be quick if someone has existing templates. However, Postgres may be unnecessary for this MVP, and CI/CD is absolutely optional. Manual deploy is likely faster and safer inside 10 hours.

Security concerns are valid but severity depends on exposure. If this is a private demo with an unlisted URL and short-lived API key budget, rate limiting can be crude. Still, `voiceId` allowlisting, size/duration validation, and no public MinIO writes are non-negotiable.

The audio-format concern is real but bounded. ffmpeg handles the common browser formats well if installed from a full image/package. The bigger issue is iOS `.wav` size. Configure AAC/M4A or low-rate mono WAV on iOS rather than assuming default PCM is safe.

### What the Investigator missed

1. ElevenLabs STS output format and endpoint behavior are not confirmed. The TODO admits endpoints and params are still unconfirmed (line 183), but the whole flow assumes STS returns MP3 (lines 13, 89, 111). The first spike must prove input format, output format, latency, voice settings, error handling, and whether custom cloned voice IDs work with STS.

2. CORS for presigned MinIO downloads is load-bearing. The browser share flow must fetch the presigned MP3 into a Blob. If MinIO/Caddy CORS is wrong, `<audio>` playback and `fetch(audioUrl)` may fail even though the object exists.

3. The public URL for presigned MinIO can be wrong behind Docker/Caddy. If boto3 signs URLs using an internal container hostname like `http://minio:9000`, clients cannot fetch them. Endpoint URL, external host, scheme, and path-style addressing must be configured explicitly.

4. Mobile recording support in iOS Safari is not guaranteed to match desktop assumptions. `MediaRecorder` support and MIME choices need a quick test on the exact iPhone/Safari target. If recording fails on mobile web, native iOS or file upload fallback becomes more important.

5. Voice cloning candidate list includes public figures (line 137). That creates reputational/platform risk and possible policy risk. For a demo, use consenting teammates or clearly fictional/accent/style voices instead of identifiable real people.

6. No mention of content moderation or consent. The example at line 10 is intentionally goofy, but voice transformation apps can generate abusive or impersonation content. For a closed hackathon, this can be handled by scope and demo discipline, but it should influence the choice of voices.

7. There is no explicit local development plan. The team needs `.env.example`, one command to run backend/frontend, and a mock conversion mode so frontend/iMessage can build while ElevenLabs or infra is down.

8. There is no observability plan. At minimum, log request ID, upload MIME/size/duration, selected voice, ffmpeg result, ElevenLabs latency/status, object key, and share ID. Otherwise integration failures will consume the demo day.

9. The plan assumes the share page can play from object storage, but some browsers block audio autoplay. The page should require an explicit play tap; this is normal, but demo script should account for it.

10. The plan does not define generated clip titles. `title` appears in the response (line 27) and share page (line 30), but no source is specified. Use a deterministic default like `"voiceMix clip"` or derive from selected voice; do not block on user-entered titles.

## Role 3 — Judge

### Blocking issues

1. **Define the real MVP/demo path before coding.** The TODO leaves "demo done" open (line 188). Decide whether the must-ship path is web record -> STS -> playback -> Web Share file into Messages, with native iMessage and custom clones as stretch. Without this, the plan has no stable finish line.

2. **Tighten the API contract in hour 0.** Lines 23-32 are not enough. Lock: multipart request shape, `voiceId` allowlist, synchronous response for MVP, `{ id, shareUrl, audioUrl, title, contentType, filename }`, and a simple error shape. Add either `GET /api/voices` or a checked-in voices JSON file.

3. **Fix durable storage semantics.** Do not store presigned `audioUrl` as the durable Postgres value as implied by line 65. Store object key + metadata; generate fresh audio URLs for responses/share pages, or proxy audio through the backend.

4. **Run the ElevenLabs spike first.** The TODO at line 183 is critical. Prove STS endpoint, auth, accepted input format, output format, latency, stock voice ID, and one cloned/custom voice ID path before building around assumptions in lines 13 and 89.

5. **Demote native iMessage unless setup is already known-good.** Lines 38 and 125 overstate the certainty of inline playable iMessage attachment delivery. Use web file sharing as the reliable baseline (line 197), and treat native iMessage as a parallel stretch/demo bonus unless provisioning/device testing is completed in hour 0-1.

6. **Validate mobile web recording and sharing on the target device early.** The plan relies on `getUserMedia`, `MediaRecorder`, `navigator.share({ files })`, and Messages accepting the file (lines 39-40, 197). This must be tested before the backend is polished.

### Should-fix issues

- Simplify infrastructure for the 10-hour window. Postgres + MinIO + Caddy + GitHub Actions is plausible but heavy (lines 60-67, 208-215). Prefer manual deploy and the fewest moving pieces that preserve HTTPS and public audio access.
- Make MinIO/Caddy external URL and CORS explicit. Presigned URLs must be fetchable by browsers and must use the public HTTPS host, not an internal Docker hostname.
- Add minimal abuse controls: server-side duration check with ffprobe, upload size cap, `voiceId` allowlist, basic IP/session rate limit, and private write-only server access to object storage.
- Add a fallback voice plan. If the 6-hour cloning jobs slip (lines 120-121, 166), ship stock voices or teammate-consented instant clones.
- Decide the app/repo structure now. Lines 52-54 are unresolved and will create friction once web and iOS work begins.
- Configure iOS recording intentionally. The line 64 PCM `.wav` assumption may create large files; set mono, sample rate, and format deliberately.
- Define routing ownership: React should own `/share/:id`, or FastAPI should server-render it, but the plan currently points both directions (lines 62-63).
- Add minimal logging around every conversion step so integration bugs are diagnosable during the 10-hour push.

### Minor / nits

- Timeline phase numbering jumps from 2 to 5 and 6 (lines 123-127), and stage headings have typos ("converence", "Stagfe"; lines 164, 168). Not technically important, but cleaning it up will make coordination easier.
- "principles on" and "once finishes, help german with" are incomplete bullets in John's track (lines 147-149).
- The example content at line 10 may be fine internally, but the public demo script should avoid phrasing that distracts from the product.
- `url` vs `audioUrl` naming is ambiguous (line 27). Use `shareUrl` and `audioUrl`.
- "ElevenLabs is the sole external dependency" (line 105) ignores GitHub Actions/GHCR if CI/CD is used (lines 208-215). Minor, but worth clarifying.

### False alarms

- **"File-first sharing is impossible."** Dismissed. The web and iMessage file-first approach is viable enough for a demo if tested early. The plan's fallback link design is the right escape hatch.
- **"Presigned URLs cannot be used."** Dismissed. They can be used, but they should be generated fresh from durable object keys rather than stored as permanent metadata.
- **"The project needs a full async job system."** Dismissed for now. Start synchronous for the steel thread. Add async only if the ElevenLabs spike shows unacceptable latency or gateway timeouts.
- **"Postgres is always overkill."** Dismissed. It is not wrong, just probably unnecessary for a 10-hour MVP. If the team already has a template, it is acceptable.
- **"Native iMessage should be removed."** Dismissed. It is a good parallel stretch track. The mistake would be making it the only definition of demo success.

### Overall assessment

The plan has the right philosophy: steel thread first, stock voices before custom clones, file-first sharing with link fallback, and parallel tracks. It is not yet sound enough to execute unchanged because the demo finish line, API contract, presigned URL semantics, ElevenLabs spike, and iMessage risk are still load-bearing ambiguities. Fix those in the first hour, explicitly make web share the baseline demo, and treat custom voices/native iMessage as upside. With those changes, the 10-hour build becomes aggressive but plausible; without them, the team is likely to lose the day to integration and platform surprises.
