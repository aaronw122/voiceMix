# Tribunal Review — voiceMix Build Plan

You are running a **tribunal review** on the file `plan.md` in this repo (`/Users/aaron/code/personal/Projects/voiceMix/plan.md`). Read it in full first.

A tribunal is an adversarial three-role analysis. Run all three roles yourself, in order, thinking hard at each stage:

## Role 1 — Investigator
Read the plan carefully and surface every issue you can find. Look for:
- **Technical errors** — wrong API claims, infeasible steps, incorrect assumptions about ElevenLabs STS, Web Share API, iMessage/MSMessages framework, MinIO/presigned URLs, ffmpeg, Caddy/TLS, Docker Compose, GitHub Actions.
- **Inconsistencies** — places where the plan contradicts itself (contract shape, audio formats, roles, timeline, scope).
- **Schedule/feasibility risk** — is a 10-hour, 3-person build with these tracks realistic? Where are the hidden time sinks? Is the critical path (6h cloning jobs) correctly identified and protected?
- **Contract/architecture gaps** — does the `/convert` + `/share/:id` contract actually let the three tracks parallelize? Missing error states, auth, rate limits, validation, presigned-URL expiry, CORS, secure-origin requirements.
- **iMessage specifics** — Apple signing/provisioning realities, whether `insertAttachment` produces an inline-playable audio bubble, simulator-vs-device testing.
- **Anything unstated but load-bearing** — assumptions that, if wrong, sink the plan.

## Role 2 — Devil's Advocate
Now challenge the Investigator's findings. For each:
- Is it actually a real problem, or pedantic noise for a 10-hour hackathon-style build?
- Is the severity right? Could a finding be overblown or understated?
- What did the Investigator MISS? Add new issues the first pass didn't catch.
- Push back on the plan's optimism AND on the Investigator's pessimism.

## Role 3 — Judge
Synthesize a final verdict:
- **Blocking issues** — must fix before starting, or the build fails. (Ranked, most critical first.)
- **Should-fix issues** — real risks worth addressing, not fatal.
- **Minor/nits** — worth noting, low priority.
- **False alarms** — things the Investigator flagged that you're dismissing, with reasoning.
- **Overall assessment** — is this plan sound enough to execute? One paragraph.

## Output
Write your full tribunal (all three roles + verdict) to `notes/tribunal-output.md`. Be concrete and cite specific lines/sections of the plan. Prioritize substance over volume — a sharp, well-reasoned review beats an exhaustive one.
