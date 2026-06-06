# Voice Engines Summary

## TL;DR

- **Use ElevenLabs for generic voices**: stock voices + Instant Voice Cloning are the reliable hackathon spine.
- **Do not depend on ElevenLabs for celebrity cloning**: Professional Voice Cloning requires live voice verification, so found audio cannot pass.
- **Celebrity/impression voices need open source**: use Whisper + CosyVoice2 or GPT-SoVITS on Modal if the quality/latency spike clears early.
- **Rights risk is publicity, not copyright**: generic characters are safest; living celebrities are highest risk; long-dead public figures are still state-dependent.
- **Infra money is manageable; setup time is the risk**: Modal reduces ops pain, but CUDA/weights/serving can still threaten a 10-hour build.

## Rights / Legal Reality

- A voice is **not copyrightable**. The relevant issue is usually **right of publicity**: control over commercial use of voice/likeness.
- **Living celebrities** are high risk. They may have publicity claims and may be aggressive about AI voice clones.
- **Long-dead public figures** are lower risk, but there is no clean universal rule. Post-mortem publicity rights vary by state.
  - Example from the brief: California lasts **70 years after death**; some states have no post-mortem right.
- **Generic characters** such as old man, baby, villain, valley girl, or robot carry effectively zero rights risk.
- For a hackathon, the practical platform risk is likely bigger than lawsuit risk: **ElevenLabs may ban the API key/account** if real-person cloning trips their enforcement.
- Self-hosted open-source tools do not enforce rights. That lowers platform-ban risk, but the rights burden moves to us.

## ElevenLabs IVC vs PVC

ElevenLabs has two cloning paths, but only one is usable for found-audio hackathon workflows.

| ElevenLabs path | Input | Quality / behavior | Celebrity viability | Why it matters |
| --- | --- | --- | --- | --- |
| **Instant Voice Cloning (IVC)** | Found audio + consent checkbox | Instant; quality plateaus after a few minutes of sample | **Unreliable** for high-profile figures | Has a no-go classifier, especially for politicians and celebrities |
| **Professional Voice Cloning (PVC)** | 30 min-3 hr clean single-speaker audio + live verification | Higher fidelity; hours to train | **Not viable** for celebrities from found audio | Requires a live voice-match captcha against the uploaded samples |

### Why PVC Can't Do Celebrities

PVC is **identity-locked**, not just rights-gated. ElevenLabs requires the speaker to record a live prompt, then compares that recording's voice profile against the uploaded samples. Public-domain status does not help because the check is verifying speaker identity.

Manual verification exists, but the brief frames it as an accessibility/edge-case path for the actual voice owner, not a loophole for found audio. Legit pro-grade celebrity voices on ElevenLabs come through licensed **Iconic Voices** estate/business deals, not self-serve cloning.

## Open-Source Options

Open-source/self-hosted options are the realistic route for celebrity/impression voices. They need GPU infrastructure and carry the same rights responsibility.

### STS Route

Speech-to-speech / voice conversion keeps the sender's recording and swaps voice characteristics.

| Tool | What it does | Strength | Limitation |
| --- | --- | --- | --- |
| **RVC** | Retrieval-based voice conversion | Canonical open-source STS; trains on found audio; no platform gate | Mostly swaps **timbre**; keeps the user's accent/cadence |
| **Seed-VC** | Voice conversion with timbre, prosody, and mannerisms | Closest open-source match to ElevenLabs STS; real-time around 400ms in the brief | Still needs GPU/self-hosting setup |
| **CosyVoice2** | Includes voice-conversion mode | Candidate for stronger conversion pipeline | Brief does not fully benchmark this route |

Key implication: **RVC-JFK sounds like JFK's tone color with the user's delivery**. The recognizable accent and cadence do not come for free.

### ASR -> TTS Route

ASR -> TTS regenerates the message in the target voice and delivery.

Pipeline: **Whisper transcription -> few-shot TTS synthesis**.

| Tool | Role | Why it is interesting | Tradeoff |
| --- | --- | --- | --- |
| **GPT-SoVITS** | Few-shot TTS | Separates content/timbre; GPT predicts prosody; brief says it can capture tone, accent, speaking style with ~1 min reference | Regenerates from text, so user delivery is discarded |
| **CosyVoice2-0.5B** | Streaming TTS | Real-time streaming; ~150ms first packet in the brief; emotional control | Still adds ASR + model setup complexity |
| **F5-TTS / IndexTTS-2 / Fish Speech V1.5** | Other TTS candidates | Mentioned as options | Not deeply evaluated in the brief |

This route best supports a **celebrity impression** because it can regenerate accent and cadence. The cost is that it no longer preserves the user's actual delivery, and Whisper may mangle slang or names.

## Infra Cost

- **GPU need**: a single 16-24GB GPU should run Whisper plus GPT-SoVITS or CosyVoice2.
  - Examples from the brief: RTX 4090/3090, A10G, L4.
- **Cloud GPU money**: roughly **$0.20-$0.70/hr** on Vast/RunPod; about **$5-$10** for a 10-hour hackathon.
- **Real cost**: time and complexity. Expect **1-3 hours** for CUDA/torch/weights/serving setup, plus a second service to operate.
- **Modal advantage**: serverless GPU, scales to zero, pay-per-second, and lets us write an inference function instead of operating a box.
- **After the demo**: an always-warm cloud GPU could be roughly **$300-$500/month**, unlike ElevenLabs' zero-idle pay-per-use model.

## Latency

Expected ASR -> TTS latency on Modal:

| Scenario | Expected latency | Notes |
| --- | --- | --- |
| Warm short clip, about 10s | **~4-8s end-to-end** | Whisper ~0.5-1.5s, TTS ~2-5s, upload/store <2s |
| ElevenLabs STS reference point | **~1-3s** | Faster, roughly 2-3x lower latency |
| Full 60s message | **~10-20s TTS** | Output length matters; the <=1 min cap helps |
| Cold start | **~15-45s** | Container spin-up + weight load |

GPU tier matters:

- **T4**: ~6-10s warm.
- **A10G/L4**: ~4-7s warm.
- **A100/4090**: ~2-4s warm.

Mitigations:

- Bake weights into the Modal image.
- Load once in `@modal.enter()`.
- Use `keep_warm=1` during the live demo.
- Consider CosyVoice2 streaming if perceived latency becomes the problem.

Because the product flow is async "record -> tap send -> it cooks -> drops in chat," warm latency is acceptable. The main demo risk is cold start on stage.

## Chosen Hybrid Architecture

Two endpoints, same `{ url, title, audioUrl }` response — frontend/iMessage pick by the chosen voice and don't care which engine ran. Splitting them also keeps ownership clean (german owns `/convert`, john owns `/impersonate`).

| Path | Endpoint | Input | Voice types | Engine | Behavior | Risk posture |
| --- | --- | --- | --- | --- | --- | --- |
| **Path A** | `POST /convert` | audio only | Generic voices: accents, ages, genders, characters | ElevenLabs stock + IVC | Keeps the sender's delivery | Reliable spine; zero infra; lowest rights risk |
| **Path B** | `POST /impersonate` | audio **or** text | Celebrity / impression voices | Whisper + **CosyVoice2 or GPT-SoVITS** on Modal | Regenerates in the target delivery with accent/cadence | Needs early quality + latency spike; fallback required |

The two paths intentionally behave differently:

- **Path A** preserves the user's delivery and changes the voice. It is genuinely speech-to-speech.
- **Path B** prioritizes the impression and regenerates delivery from text. It is **not forced to be STS** — it transcribes to text internally, so it can accept text directly (skipping Whisper avoids transcription errors and lowers latency).

Graceful degradation is built in: if Path B does not clear quality or latency early, the app can still ship generic voices through Path A. A lower-fidelity IVC celebrity fallback may exist, but it is not reliable enough to be the core plan.
