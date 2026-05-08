#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
SOURCE_AUDIO="$ROOT_DIR/song.mp3"
FLAG_AUDIO="$ROOT_DIR/flag.mp3"
FLAG_TEXT=""
PREVIEW_PATH=""
TAG_HINT="Do you know FFT?"
UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"

usage() {
  cat <<'EOF'
Usage:
  scripts/build_dist.sh [--input song.mp3] [--output flag.mp3] [--flag-text 'miniL{...}'] [--preview preview.png]

Behavior:
  1. Generate flag.mp3 from song.mp3 with scripts/spectrogram_flag.py.
  2. Set both encoder and encoded_by to "Do you know FFT?" on flag.mp3.
  3. Pack flag.mp3 into dist/flag.enc with wyy.
  4. Copy the built wyy binary into dist/wyy.

Defaults:
  --input song.mp3
  --output flag.mp3

Outputs:
  flag.mp3
  dist/wyy
  dist/flag.enc
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input)
      SOURCE_AUDIO="$2"
      shift 2
      ;;
    --output)
      FLAG_AUDIO="$2"
      shift 2
      ;;
    --flag-text)
      FLAG_TEXT="$2"
      shift 2
      ;;
    --preview)
      PREVIEW_PATH="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

[[ "$SOURCE_AUDIO" = /* ]] || SOURCE_AUDIO="$ROOT_DIR/$SOURCE_AUDIO"
[[ "$FLAG_AUDIO" = /* ]] || FLAG_AUDIO="$ROOT_DIR/$FLAG_AUDIO"
[[ -z "$PREVIEW_PATH" || "$PREVIEW_PATH" = /* ]] || PREVIEW_PATH="$ROOT_DIR/$PREVIEW_PATH"

if [[ ! -f "$SOURCE_AUDIO" ]]; then
  echo "Input audio not found: $SOURCE_AUDIO" >&2
  exit 1
fi

if [[ -z "$FLAG_TEXT" && ! -f "$FLAG_AUDIO" ]]; then
  echo "Need --flag-text to generate $FLAG_AUDIO, or provide an existing file there." >&2
  exit 1
fi

if [[ -n "$FLAG_TEXT" ]]; then
  spectro_cmd=(
    uv run "$ROOT_DIR/scripts/spectrogram_flag.py"
    "$SOURCE_AUDIO"
    "$FLAG_AUDIO"
    "$FLAG_TEXT"
  )
  if [[ -n "$PREVIEW_PATH" ]]; then
    spectro_cmd+=(--preview "$PREVIEW_PATH")
  fi
  UV_CACHE_DIR="$UV_CACHE_DIR" "${spectro_cmd[@]}"
fi

if [[ "${FLAG_AUDIO##*.}" == "mp3" ]]; then
  UV_CACHE_DIR="$UV_CACHE_DIR" uv run --with mutagen python - <<PY
from mutagen.id3 import ID3, TENC, TSSE

path = r"$FLAG_AUDIO"
hint = r"$TAG_HINT"
tag = ID3(path)
tag.delall("TENC")
tag.delall("TSSE")
tag.add(TENC(encoding=3, text=hint))
tag.add(TSSE(encoding=3, text=hint))
tag.save(v2_version=4)
PY
fi

mkdir -p "$DIST_DIR"
cargo build --release --manifest-path "$ROOT_DIR/wyy/Cargo.toml"
cp "$ROOT_DIR/wyy/target/release/wyy" "$DIST_DIR/wyy"
"$ROOT_DIR/wyy/target/release/wyy" pack "$FLAG_AUDIO" "$DIST_DIR/flag.enc"

echo "Built:"
echo "  $FLAG_AUDIO"
echo "  $DIST_DIR/wyy"
echo "  $DIST_DIR/flag.enc"
