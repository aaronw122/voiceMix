# Voice pipeline — data fetching

Pull clean single-speaker audio off YouTube → canonical WAV masters for Seed-VC / RVC.

## The tool

We don't hand-roll a scraper. **`yt-dlp`** (the maintained `youtube-dl` fork) already
solves YouTube's signature ciphers, throttling, and format selection — a DIY
`requests`/`bs4` scraper breaks the moment YT ships a cipher change. `fetch_audio.py` is
a thin wrapper that drives `yt-dlp` (download) + `ffmpeg` (normalize) and forces output
into one master format.

### Install (one-time)

```bash
uv tool install yt-dlp        # or: brew install yt-dlp / pipx install yt-dlp
brew install ffmpeg deno      # deno = JS runtime yt-dlp needs for best formats
# optional, only for --demucs (music/SFX removal):
uv tool install demucs
```

> **Why deno?** Without a JS runtime + the EJS challenge solver, yt-dlp can't solve
> YouTube's "n challenge" and silently serves *lower-bitrate* audio — bad for clone
> source fidelity. `fetch_audio.py` enables the solver by default (`--remote-components
> ejs:github`); disable with `--no-remote-components`.

## Usage

```bash
cd pipeline

# whole video → data/raw/<title>.wav  (48k mono s16le, loudnorm'd)
python3 fetch_audio.py "https://www.youtube.com/watch?v=XXXX"

# just a clean span (skip applause/Q&A) — HH:MM:SS:
python3 fetch_audio.py "<url>" --section 00:01:30-00:14:00 --name jobs_stanford

# narration buried under music/SFX (Attenborough docs) → isolate vocals:
python3 fetch_audio.py "<url>" --demucs

# batch a list (one URL per line, # comments ok):
python3 fetch_audio.py --batch attenborough.txt --demucs
```

Run `python3 fetch_audio.py -h` for all flags.

## Output contract

One **master** per source: `WAV / PCM s16le / mono / 48000 Hz`, loudness-normalized to
−16 LUFS. 48k because RVC trains up to 48k and Seed-VC downsamples to 22050 internally —
keep one high-fidelity master, downsample per-engine downstream.

**This is the master, not training clips.** Slicing into ≤30s (Seed-VC) / ~3s (RVC) is a
separate step — clips outside Seed-VC's 1–30s window are silently dropped, so pre-slice.

## Sourcing the three targets (quality > quantity)

Clone quality is bounded by source cleanliness: **one speaker, no music, no second voice,
no crowd.** Both engines reproduce *everything* they hear.

| Target | Good source | Watch out |
|---|---|---|
| **Steve Jobs** | 2005 Stanford commencement (single mic, ~15min, mostly clean). Keynote *demo* segments. | Trim applause/laughter with `--section`. Some keynotes have music stings. |
| **David Attenborough** | Solo **interviews** / behind-the-scenes / audiobook clips = bare voice. | Documentary narration is mixed over **music + nature SFX** → use `--demucs`, but it still leaves artifacts. Prefer interview audio if you can find it. |
| **Joe Rogan** | JRE **solo intros/ad-reads**, standup specials (him alone on mic). | The podcast is **2-speaker** — most of it is poison for cloning. Avoid guest segments, or diarize. Crowd noise on standup. |

### Workflow per target
1. Find 5–15 min of the cleanest single-speaker audio you can.
2. `fetch_audio.py` it (use `--section` to cut to clean spans; `--demucs` if music).
3. Listen back — if you hear a second voice / music / heavy reverb, re-cut.
4. Slice to clips → Seed-VC zero-shot first (needs only ONE clean ≤30s ref), RVC train only if that disappoints.

## Legal / rights note

All three are publicity-risk: Attenborough + Rogan are living (highest risk); Jobs is
California-protected (d.2011 + 70yr post-mortem). Self-hosting Seed-VC/RVC avoids a
*platform ban* but moves the rights burden onto you. Keep this to research/demo use.

`data/` is gitignored — audio is large and rights-encumbered; never commit it.
