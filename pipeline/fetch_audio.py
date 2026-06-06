#!/usr/bin/env python3
"""
fetch_audio.py — pull clean single-speaker audio off YouTube for voice-conversion
training/reference data (Seed-VC / RVC).

This is a thin wrapper around `yt-dlp` (download) + `ffmpeg` (normalize). It does NOT
reimplement a YouTube scraper — yt-dlp already solves signature ciphers, throttling,
and format selection; rolling your own with requests/bs4 breaks the moment YT ships a
cipher change. We just orchestrate it and force the output into the canonical master
format the pipeline expects.

OUTPUT CONTRACT (one high-fidelity master per source):
  WAV / PCM s16le / mono / 48000 Hz   (RVC trains up to 48k; Seed-VC downsamples to
  22050 internally — keep one 48k master, downsample per-engine downstream).

This is the *master*. Slicing into 1–30s clips (Seed-VC) or 3s auto-slices (RVC) is a
SEPARATE step — see slice_audio.py / your engine's preprocessor. Don't slice here.

USAGE
  python fetch_audio.py <url> [<url> ...] [options]
  python fetch_audio.py --batch urls.txt [options]

  # grab just a clean span (skip applause/intro) — HH:MM:SS or seconds:
  python fetch_audio.py <url> --section 00:01:30-00:14:00

  # narration over music/SFX (Attenborough) → isolate vocals with demucs first:
  python fetch_audio.py <url> --demucs

OPTIONS
  --out DIR        output dir (default: ./data/raw, relative to this file)
  --sr HZ          master sample rate (default: 48000)
  --section S-E    download only [start-end] of the video (yt-dlp --download-sections)
  --no-loudnorm    skip EBU R128 loudness normalization (on by default, -16 LUFS)
  --demucs         run demucs --two-stems=vocals to strip music/SFX before normalize
  --name NAME      override output basename (default: sanitized video title)
  --keep-tmp       don't delete the raw downloaded file

Requires: yt-dlp, ffmpeg on PATH. --demucs also requires `demucs`.
Install yt-dlp:  uv tool install yt-dlp   (or: brew install yt-dlp / pipx install yt-dlp)
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE / "data" / "raw"


def die(msg: str, code: int = 1) -> "None":
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def require(tool: str, hint: str = "") -> str:
    path = shutil.which(tool)
    if not path:
        die(f"`{tool}` not found on PATH. {hint}".rstrip())
    return path


def sanitize(name: str) -> str:
    name = re.sub(r"[^\w\s-]", "", name).strip()
    name = re.sub(r"[\s_-]+", "_", name)
    return name[:80] or "audio"


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    """Run, streaming stderr to our stderr; capture stdout."""
    return subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True, **kw)


def to_seconds(t: str) -> float:
    """'HH:MM:SS' / 'MM:SS' / 'SS' (float ok) → seconds."""
    s = 0.0
    for part in t.strip().split(":"):
        s = s * 60 + float(part)
    return s


def download(url: str, tmp: Path, remote_components: bool) -> tuple[Path, str]:
    """yt-dlp: download the FULL bestaudio (native downloader), return (file_path, title).

    NB: we deliberately do NOT use --download-sections here. That path hands byte-fetching
    to ffmpeg, whose HTTPS reader doesn't cope with YouTube throttling — it grabs one ~512KB
    buffer and hangs. The native downloader (with the EJS solver) is reliable. Section
    trimming is done by ffmpeg locally in normalize() on the already-downloaded file.
    """
    cmd = [
        "yt-dlp",
        "-f", "bestaudio/best",
        "--no-playlist",
        "-o", str(tmp / "%(id)s.%(ext)s"),
        # two --print lines (stdout, in this order); logs go to stderr:
        "--print", "%(title)s",
        "--print", "after_move:filepath",
        "--no-simulate",
    ]
    if remote_components:
        # Fetch the EJS challenge-solver from yt-dlp's GitHub so the YouTube
        # "n challenge" gets solved and the highest-bitrate formats are offered.
        # Requires a JS runtime (deno). Opt out with --no-remote-components.
        cmd += ["--remote-components", "ejs:github"]
    cmd.append(url)
    try:
        out = run(cmd).stdout.strip().splitlines()
    except subprocess.CalledProcessError as e:
        die(f"yt-dlp failed for {url} (exit {e.returncode})")
    if len(out) < 2:
        die(f"unexpected yt-dlp output for {url}: {out!r}")
    title, filepath = out[0], out[-1]
    fp = Path(filepath)
    if not fp.exists():
        die(f"yt-dlp reported {fp} but it doesn't exist")
    return fp, title


def demucs_vocals(src: Path, tmp: Path) -> Path:
    """Isolate the vocal stem (strips music/SFX). Returns the vocals wav."""
    require("demucs", "install: uv tool install demucs  (or pip install demucs)")
    outdir = tmp / "demucs"
    subprocess.run(
        ["demucs", "--two-stems=vocals", "-o", str(outdir), str(src)],
        check=True,
    )
    hits = list(outdir.glob("*/*/vocals.wav"))
    if not hits:
        die("demucs produced no vocals.wav")
    return hits[0]


def normalize(src: Path, dst: Path, sr: int, loudnorm: bool, section: str | None = None) -> None:
    """ffmpeg single pass → mono, target SR, s16le WAV, optional loudnorm + section trim."""
    af = []
    if loudnorm:
        af.append("loudnorm=I=-16:TP=-1.5:LRA=11")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    if section:
        start_s, end_s = section.split("-", 1)  # times use ':' so a single '-' splits them
        ss = to_seconds(start_s)
        cmd += ["-ss", f"{ss:.3f}"]              # input seek before -i = fast
        cmd += ["-i", str(src), "-t", f"{to_seconds(end_s) - ss:.3f}"]
    else:
        cmd += ["-i", str(src)]
    if af:
        cmd += ["-af", ",".join(af)]
    cmd += ["-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le", str(dst)]
    subprocess.run(cmd, check=True)


def process_one(url: str, args, tmp: Path) -> Path:
    raw, title = download(url, tmp, remote_components=not args.no_remote_components)
    print(f"  downloaded: {title}", file=sys.stderr)
    stem = sanitize(args.name or title)
    src = demucs_vocals(raw, tmp) if args.demucs else raw
    dst = Path(args.out) / f"{stem}.wav"
    n = 1
    while dst.exists():
        dst = Path(args.out) / f"{stem}_{n}.wav"
        n += 1
    normalize(src, dst, args.sr, loudnorm=not args.no_loudnorm, section=args.section)
    return dst


def main() -> None:
    p = argparse.ArgumentParser(description="YouTube → clean mono WAV master for voice cloning.")
    p.add_argument("urls", nargs="*", help="YouTube URLs (or video IDs)")
    p.add_argument("--batch", help="file with one URL per line (# comments ok)")
    p.add_argument("--out", default=str(DEFAULT_OUT), help=f"output dir (default: {DEFAULT_OUT})")
    p.add_argument("--sr", type=int, default=48000, help="master sample rate (default: 48000)")
    p.add_argument("--section", help='clip span, e.g. "00:01:30-00:14:00"')
    p.add_argument("--no-loudnorm", action="store_true", help="skip loudness normalization")
    p.add_argument("--demucs", action="store_true", help="strip music/SFX via demucs vocals stem")
    p.add_argument("--no-remote-components", action="store_true",
                   help="don't fetch yt-dlp's EJS challenge solver (may yield lower-bitrate audio)")
    p.add_argument("--name", help="override output basename")
    p.add_argument("--keep-tmp", action="store_true", help="keep the raw download")
    args = p.parse_args()

    require("yt-dlp", "install: uv tool install yt-dlp  (or brew install yt-dlp)")
    require("ffmpeg", "install: brew install ffmpeg")

    urls = list(args.urls)
    if args.batch:
        for line in Path(args.batch).read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                urls.append(line)
    if not urls:
        die("no URLs given (positional args or --batch)")
    if args.name and len(urls) > 1:
        die("--name only makes sense with a single URL")

    Path(args.out).mkdir(parents=True, exist_ok=True)
    tmp_root = Path(tempfile.mkdtemp(prefix="fetch_audio_"))
    done = []
    try:
        for i, url in enumerate(urls, 1):
            print(f"[{i}/{len(urls)}] {url}", file=sys.stderr)
            done.append(process_one(url, args, tmp_root))
    finally:
        if not args.keep_tmp:
            shutil.rmtree(tmp_root, ignore_errors=True)

    print("\nwrote:")
    for d in done:
        print(f"  {d}")
    print(f"\nnext: slice these masters into ≤30s clips before feeding Seed-VC/RVC.")


if __name__ == "__main__":
    main()
