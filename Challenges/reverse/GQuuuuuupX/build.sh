#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SOURCE_DIR="$ROOT/Source_Code"
HANDOUT_BIN="$ROOT/Handout/GQuuuuuupX"
DIST_BIN="$ROOT/dist/GQuuuuuupX"
ZIP_PATH="$ROOT/dist/GQuuuuuupX-handout.zip"

"$SOURCE_DIR/build.sh"

mkdir -p "$ROOT/Handout" "$ROOT/dist"
cp "$SOURCE_DIR/dist/GQuuuuuupX-packed" "$HANDOUT_BIN"
cp "$HANDOUT_BIN" "$DIST_BIN"

python3 - "$HANDOUT_BIN" "$ZIP_PATH" <<'PY'
from pathlib import Path
import sys
import zipfile

handout = Path(sys.argv[1])
archive = Path(sys.argv[2])
archive.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    zf.write(handout, arcname=handout.name)
PY

echo "handout: $HANDOUT_BIN"
echo "zip    : $ZIP_PATH"
