#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_ROOT="${RVC_DATA_ROOT:-"$SCRIPT_DIR/data/rvc"}"
VOLUME="${1:-rvc-vol}"

if [ "$#" -gt 0 ]; then
  shift
fi

if ! command -v modal >/dev/null 2>&1; then
  echo "modal CLI not found. Install/auth first: pip install modal && modal setup" >&2
  exit 1
fi

if [ "$#" -gt 0 ]; then
  speakers=("$@")
else
  speakers=()
  for dir in "$DATA_ROOT"/*; do
    if [ -d "$dir" ]; then
      speakers+=("$(basename "$dir")")
    fi
  done
fi

if [ "${#speakers[@]}" -eq 0 ]; then
  echo "No speaker folders found in $DATA_ROOT" >&2
  exit 1
fi

echo "Ensuring Modal volume exists: $VOLUME"
if ! modal volume create "$VOLUME"; then
  echo "Volume may already exist; continuing."
fi

for speaker in "${speakers[@]}"; do
  dir="$DATA_ROOT/$speaker"
  if [ ! -d "$dir" ]; then
    echo "Missing speaker folder: $dir" >&2
    exit 1
  fi

  wavs=("$dir"/*.wav)
  if [ ! -e "${wavs[0]}" ]; then
    echo "No .wav files found in $dir" >&2
    exit 1
  fi

  echo
  echo "Uploading $speaker -> /datasets/$speaker/"
  for wav in "${wavs[@]}"; do
    modal volume put --force "$VOLUME" "$wav" "/datasets/$speaker/"
  done
done

echo
echo "Uploaded datasets:"
for speaker in "${speakers[@]}"; do
  modal volume ls "$VOLUME" "/datasets/$speaker"
done
