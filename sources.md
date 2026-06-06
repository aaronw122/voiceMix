# Voice Source Data — One Person Per Archetype

Each archetype must be cloned from **a single consistent speaker** — mixing people tanks
quality (ElevenLabs clones whatever it hears; multiple voices = muddy/unstable). This doc
names a **specific individual source per archetype** wherever one exists.

## Legal reality (verified, June 2026)

- **Instant Voice Clone:** allowed for *other people* **only with their explicit consent**.
  Pulling a random podcast/YouTuber is **not** consent and is a TOS violation.
- **Professional Voice Clone:** **your own voice only** — even with consent you can't PVC
  someone else.
- **Public figures (JFK/MLK/celebs): prohibited** — accounts have been suspended.
- **Safe inputs:** CC-licensed corpora (VCTK = CC-BY 4.0), public-domain audio (LibriVox),
  and **consenting people you record yourself**.

> Clip length: Instant Clone needs only **~1–3 min** of clean audio. One VCTK speaker folder
> (~400 sentences) is far more than enough — trim to a clean minute.

## The map: archetype → specific single source

| Archetype | Source (one person) | License / how |
|---|---|---|
| **20-yo woman** | **VCTK `p225`** (23 F, English, Southern) — alt: `p228`, `p229` | CC-BY 4.0, ready |
| **20-yo man** | **VCTK `p226`** (22 M, English, Surrey) — alt: `p232`, `p254` | CC-BY 4.0, ready |
| **Indian accent (M)** | **VCTK `p251`** (26 M, Indian) — alt: `p376` (22 M) | CC-BY 4.0, ready |
| **Indian accent (F)** | **VCTK `p248`** (23 F, Indian) | CC-BY 4.0, ready |
| **Scottish accent (M)** | **VCTK `p275`** (23 M, Edinburgh/Midlothian) — alt: `p285`, `p237`, `p241` | CC-BY 4.0, ready |
| **Scottish accent (F)** | **VCTK `p262`** (23 F, Edinburgh) — alt: `p249` (Aberdeen) | CC-BY 4.0, ready |
| **85-yo man** | ❌ no clean dataset (VCTK caps at 38). **Record one consenting elderly person** (~2 min reading), or audition a single elderly-sounding **LibriVox solo narrator** (public domain) | record w/ consent |
| **Voice-cracking teen** | ❌ no dataset. **Record one consenting teen** (or do the crack yourself) | record w/ consent |
| **Baby** | ❌ uncloneable — infants don't produce intelligible speech, so a clone can't "say" your text. Clone **one young child** (consenting friend's kid) and let pitch read as babyish, or drop it | record w/ consent / cut |

**4 of 7 archetypes ship straight from VCTK** (exact single-speaker IDs above). The other 3
have **no clean single-speaker corpus** — the only reliable, legal path is recording one
willing person per archetype.

## CSTR VCTK Corpus — why it's the workhorse

~110 English speakers, **each reading ~400 sentences solo** in a treated room. The download is
organized **one folder per speaker** (`wav48_silence_trimmed/pXXX/`), so a single folder = one
clean person = a perfect clone source. Accent/age/gender come from `speaker-info.txt`.

- Download: Edinburgh DataShare (`datashare.ed.ac.uk/handle/10283/3443`) or HF `CSTR-Edinburgh/vctk`.
- License: **CC-BY 4.0** (attribute, commercial-ok).
- Pick a folder → trim ~1 clean min → feed to ElevenLabs Instant Clone.

### VCTK accent reference (pulled from `speaker-info.txt`)

- **Indian:** `p248` (F), `p251` (M), `p376` (M)
- **Scottish:** `p237 p241 p246 p247 p249 p252 p255 p260 p262(F) p263 p264(F) p265(F) p271 p272 p275 p281 p284 p285` (Edinburgh/Fife/Aberdeen/etc.)
- **Young English (20–23):** `p225(F) p226(M) p228(F) p229(F) p232(M) p243(M) p254(M) p258(M) p259(M) p269(F)`
- **American:** `p294 p295 p334 p339 p345 p360 p361 p362` and `p333` (19 F, Indiana)
- **Irish / N. Irish:** `p245 p266 p283 p288 p295` / `p238 p261 p292 p293 p304`
- **Age range of entire corpus: 18–38** → no elderly, no children, no babies.

## The three gap archetypes — concrete plan

No corpus has clean isolated **elderly / pre-teen-crack / infant** speech that clones well.
Reliable + legal options, in order:

1. **Record a consenting person** (best): a grandparent for the 85-yo, a younger sibling/cousin
   for the teen or child. 2 min of clean reading in a quiet room. This is also the only path
   that's unambiguously TOS-clean.
2. **LibriVox solo recordings** (public domain) for an older-male timbre — browse solo projects
   and **audition** narrators; pick ONE whose voice fits, use only that reader's audio.
3. **Skip baby** for the demo if no child source — ElevenLabs can't make a real infant talk.

## Sourcing checklist (per voice)

- [ ] Exactly one speaker, start to finish — no second voice, laughter, music, reverb.
- [ ] Clean ~1–3 min; read speech > conversational for clone stability.
- [ ] License/consent clear: VCTK (CC-BY) ✓ · LibriVox (PD) ✓ · recorded-with-consent ✓ · random web ✗.
- [ ] Trim to the cleanest minute before uploading to ElevenLabs Instant Clone.

## Links

- VCTK (DataShare): https://datashare.ed.ac.uk/handle/10283/3443
- VCTK (Hugging Face): https://huggingface.co/datasets/CSTR-Edinburgh/vctk
- LibriVox: https://librivox.org/
- ElevenLabs — cloning restrictions: https://help.elevenlabs.io/hc/en-us/articles/13313778519057
- ElevenLabs — can't PVC someone else: https://help.elevenlabs.io/hc/en-us/articles/36842751624209
