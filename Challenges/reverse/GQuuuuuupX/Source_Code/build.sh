#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
DIST="$ROOT/dist"
SRC="$ROOT/src/main.c"
PLAIN="$DIST/GQuuuuuupX"
PACKED="$DIST/GQuuuuuupX-packed"
UNPACKED="$DIST/GQuuuuuupX-unpacked"
PATCHED_UPX="$DIST/upx-stub-patched"
VENDOR_UPX="$ROOT/vendor/upx-stub-patched"

UPX_SOURCE_BIN="${UPX_BIN:-}"
if [[ -z "$UPX_SOURCE_BIN" && -x "$VENDOR_UPX" ]]; then
    UPX_SOURCE_BIN="$VENDOR_UPX"
fi
if [[ -z "$UPX_SOURCE_BIN" && -x "$PATCHED_UPX" ]]; then
    UPX_SOURCE_BIN="$PATCHED_UPX"
fi
if [[ -z "$UPX_SOURCE_BIN" ]]; then
    UPX_SOURCE_BIN="$(command -v upx || true)"
fi
if [[ -z "$UPX_SOURCE_BIN" ]]; then
    echo "upx not found; set UPX_BIN to a compatible UPX 5.1.1 binary" >&2
    exit 1
fi

mkdir -p "$DIST"

python3 "$ROOT/scripts/sync_challenge.py"
gcc -O0 -fno-pie -no-pie -s -o "$PLAIN" "$SRC"
python3 "$ROOT/scripts/patch_stub.py" "$UPX_SOURCE_BIN" "$PATCHED_UPX"
"$PATCHED_UPX" -9 -f -o "$PACKED" "$PLAIN"
"$PATCHED_UPX" -d -f -o "$UNPACKED" "$PACKED"
cmp -s "$PLAIN" "$UNPACKED"
python3 "$ROOT/scripts/verify.py"
