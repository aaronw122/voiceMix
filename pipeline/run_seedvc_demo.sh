#!/usr/bin/env bash
# Seed-VC zero-shot smoke test: one source utterance → 3 target timbres.
# Builds out/index.html with audio players and opens it.
set -euo pipefail

ROOT="/Users/john/Dev/voiceMix/pipeline"
SVC="$ROOT/seed-vc"
PY="$SVC/.venv/bin/python"
CLIPS="$ROOT/data/clips"
OUT="$ROOT/out"
export PYTORCH_ENABLE_MPS_FALLBACK=1   # let unsupported MPS ops fall back to CPU

# --- source: an Obama clip (the "words"); rendered into the 3 target voices ---
SRC="$CLIPS/Barack_Obama_describes_his_experience_writing_A_Promised_Land/Barack_Obama_describes_his_experience_writing_A_Promised_Land_0001.wav"

# --- reference (timbre) clip per target ---
ATT="$CLIPS/Sir_David_Attenborough_A_message_to_world_leaders/Sir_David_Attenborough_A_message_to_world_leaders_0006.wav"
HER="$CLIPS/Every_Man_for_Himself_and_God_Against_All_A_Memoir_Audiobook_by_Werner_Herzog/Every_Man_for_Himself_and_God_Against_All_A_Memoir_Audiobook_by_Werner_Herzog_0041.wav"
# JFK: longest clip in the _1 folder (computed)
JFK="$(ls -S "$CLIPS/Eleanor_Roosevelt_interviews_JFK_1"/*.wav | head -1)"

mkdir -p "$OUT"
cp "$SRC" "$OUT/_source_obama.wav"

run() {  # name  reffile
  local name="$1" ref="$2"
  echo ">>> converting → $name"
  rm -rf "$OUT/$name"; mkdir -p "$OUT/$name"
  ( cd "$SVC" && "$PY" inference.py \
      --source "$SRC" --target "$ref" --output "$OUT/$name" \
      --diffusion-steps 25 --length-adjust 1.0 --inference-cfg-rate 0.7 \
      --f0-condition False --fp16 False )
}

run attenborough "$ATT"
run herzog       "$HER"
run jfk          "$JFK"

# --- build a dead-simple player page ---
HTML="$OUT/index.html"
{
  echo '<!doctype html><meta charset=utf-8><title>Seed-VC demo</title>'
  echo '<style>body{font:16px system-ui;max-width:640px;margin:40px auto;padding:0 16px}'
  echo 'h1{font-size:20px}section{margin:18px 0;padding:14px;border:1px solid #ddd;border-radius:10px}'
  echo 'h2{margin:0 0 8px;font-size:15px}audio{width:100%}small{color:#666}</style>'
  echo '<h1>Seed-VC zero-shot — same words, different voice</h1>'
  echo "<p><small>source content = Obama clip, repainted into each target's timbre. diffusion-steps 25, cfg 0.7, f0 off.</small></p>"
  echo '<section><h2>▶︎ SOURCE (Obama — the input words/delivery)</h2><audio controls src="_source_obama.wav"></audio></section>'
  for name in attenborough herzog jfk; do
    f=$(ls "$OUT/$name"/*.wav 2>/dev/null | head -1)
    [ -n "$f" ] && echo "<section><h2>→ ${name}</h2><audio controls src=\"${name}/$(basename "$f")\"></audio></section>"
  done
} > "$HTML"

echo "=== done. outputs in $OUT ==="
ls -R "$OUT" | sed 's/^/  /'
open "$HTML"
