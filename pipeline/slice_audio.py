#!/usr/bin/env python3
"""
slice_audio.py — cut clean WAV masters into Seed-VC-ready training clips.

WHY: Seed-VC silently DROPS any training clip outside 1–30s. A 15-min master = one
oversized file Seed-VC ignores. This splits on silence into natural utterance-length
clips, drops the too-short, and chops the too-long — so every output is in-window.

(RVC does NOT need this — its preprocess auto-slices to ~3s. Point RVC at data/raw
directly. This script is for the Seed-VC path.)

No pydub on purpose: `audioop` was removed from stdlib in Python 3.13 (you're on 3.14),
so pydub is broken here. We drive `ffmpeg silencedetect` directly — no audio deps.

USAGE
  python slice_audio.py                       # data/raw/*.wav  -> data/clips/<stem>/
  python slice_audio.py data/raw/jobs.wav     # one file
  python slice_audio.py --in data/raw --out data/clips

OUTPUT: data/clips/<master_stem>/<stem>_0001.wav, ... (mono, master's SR/codec)

TUNING
  --noise -30dB     silence threshold (quieter rooms: -35..-40; noisy: -25)
  --min-silence 0.4 seconds of silence that counts as a split point
  --min-dur 1.0     drop clips shorter than this (Seed-VC floor)
  --max-dur 30.0    hard-split clips longer than this (Seed-VC ceiling)
  --pad-ms 100      keep this much edge on each side so cuts don't clip words
"""
from __future__ import annotations

import argparse
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_IN = HERE / "data" / "raw"
DEFAULT_OUT = HERE / "data" / "clips"

SIL_START = re.compile(r"silence_start:\s*([0-9.]+)")
SIL_END = re.compile(r"silence_end:\s*([0-9.]+)")


def die(msg: str) -> "None":
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def require(tool: str) -> None:
    if not shutil.which(tool):
        die(f"`{tool}` not found on PATH.")


def duration_of(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        stdout=subprocess.PIPE, text=True, check=True,
    ).stdout.strip()
    return float(out)


def detect_silences(path: Path, noise: str, min_silence: float) -> list[tuple[float, float]]:
    """Return list of (silence_start, silence_end) via ffmpeg silencedetect."""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path),
         "-af", f"silencedetect=noise={noise}:d={min_silence}", "-f", "null", "-"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    log = proc.stderr
    starts = [float(m) for m in SIL_START.findall(log)]
    ends = [float(m) for m in SIL_END.findall(log)]
    # silencedetect emits start then (later) end; if the file ends mid-silence the
    # trailing start has no matching end — pair what we can, in order.
    sils: list[tuple[float, float]] = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else None
        sils.append((s, e if e is not None else s))
    return sils


def speech_spans(total: float, sils: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Complement of the silence intervals = the speech we keep."""
    spans: list[tuple[float, float]] = []
    cursor = 0.0
    for s, e in sils:
        if s > cursor:
            spans.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < total:
        spans.append((cursor, total))
    return spans


def chunk(spans: list[tuple[float, float]], min_dur: float, max_dur: float,
          pad: float, total: float) -> tuple[list[tuple[float, float]], int]:
    """Pad edges, drop too-short, hard-split too-long. Returns (clips, dropped)."""
    clips: list[tuple[float, float]] = []
    dropped = 0
    for a, b in spans:
        a = max(0.0, a - pad)
        b = min(total, b + pad)
        dur = b - a
        if dur < min_dur:
            dropped += 1
            continue
        if dur <= max_dur:
            clips.append((a, b))
            continue
        # too long → split into equal sub-clips each <= max_dur
        n = math.ceil(dur / max_dur)
        step = dur / n
        for k in range(n):
            clips.append((a + k * step, a + (k + 1) * step))
    return clips, dropped


def extract(src: Path, clips: list[tuple[float, float]], outdir: Path, stem: str) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    width = max(4, len(str(len(clips))))
    for i, (a, b) in enumerate(clips, 1):
        dst = outdir / f"{stem}_{str(i).zfill(width)}.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-ss", f"{a:.3f}", "-i", str(src), "-t", f"{b - a:.3f}",
             "-ac", "1", "-c:a", "pcm_s16le", str(dst)],
            check=True,
        )


def process(src: Path, outroot: Path, args) -> tuple[int, int, float]:
    total = duration_of(src)
    sils = detect_silences(src, args.noise, args.min_silence)
    spans = speech_spans(total, sils)
    clips, dropped = chunk(spans, args.min_dur, args.max_dur, args.pad_ms / 1000.0, total)
    if not clips:
        print(f"  ! {src.name}: 0 clips (try a quieter --noise or longer --min-silence)",
              file=sys.stderr)
        return 0, dropped, 0.0
    stem = src.stem
    extract(src, clips, outroot / stem, stem)
    kept_dur = sum(b - a for a, b in clips)
    print(f"  {src.name}: {len(clips)} clips, {kept_dur:.0f}s kept, {dropped} dropped (<{args.min_dur}s)")
    return len(clips), dropped, kept_dur


def main() -> None:
    p = argparse.ArgumentParser(description="Silence-split WAV masters into Seed-VC clips (1–30s).")
    p.add_argument("inputs", nargs="*", help="master wav file(s); default: all wavs in --in")
    p.add_argument("--in", dest="indir", default=str(DEFAULT_IN), help=f"input dir (default: {DEFAULT_IN})")
    p.add_argument("--out", default=str(DEFAULT_OUT), help=f"output dir (default: {DEFAULT_OUT})")
    p.add_argument("--noise", default="-30dB", help="silence threshold (default: -30dB)")
    p.add_argument("--min-silence", type=float, default=0.4, help="min silence to split on, s (default: 0.4)")
    p.add_argument("--min-dur", type=float, default=1.0, help="drop clips shorter than this, s (default: 1.0)")
    p.add_argument("--max-dur", type=float, default=30.0, help="hard-split clips longer than this, s (default: 30.0)")
    p.add_argument("--pad-ms", type=float, default=100, help="edge padding per side, ms (default: 100)")
    args = p.parse_args()

    require("ffmpeg")
    require("ffprobe")

    if args.inputs:
        files = [Path(x) for x in args.inputs]
    else:
        files = sorted(Path(args.indir).glob("*.wav"))
    files = [f for f in files if f.exists()]
    if not files:
        die(f"no input wavs (looked in {args.indir} / args)")

    outroot = Path(args.out)
    print(f"slicing {len(files)} master(s) → {outroot}")
    tot_clips = tot_drop = 0
    tot_dur = 0.0
    for f in files:
        c, d, dur = process(f, outroot, args)
        tot_clips += c
        tot_drop += d
        tot_dur += dur

    print(f"\ntotal: {tot_clips} clips, {tot_dur:.0f}s ({tot_dur/60:.1f} min), {tot_drop} dropped")
    print(f"feed a target's folder to Seed-VC:  --dataset-dir {outroot}/<stem>")


if __name__ == "__main__":
    main()
