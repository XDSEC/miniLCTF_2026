#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path


STUB_PREFIX_LEN = 0x740


@dataclass(frozen=True)
class StubPatch:
    rel_offset: int
    old: bytes
    new: bytes


PATCHES = (
    StubPatch(0x76C, bytes.fromhex("f30f1efa"), bytes.fromhex("0f0541c6")),
    StubPatch(0x774, bytes.fromhex("0f055a58"), bytes.fromhex("45a0375a")),
    StubPatch(0x786, bytes.fromhex("3effe090"), bytes.fromhex("58ffe090")),
    StubPatch(0x7B6, bytes.fromhex("f30f1efa"), bytes.fromhex("0f0541c6")),
)


def find_stub_header() -> Path:
    start = Path(__file__).resolve()
    for path in (start.parent, *start.parents):
        candidate = path / ".vendor" / "upx-src" / "src" / "stub" / "amd64-linux.elf-fold.h"
        if candidate.exists():
            return candidate
    raise SystemExit("unable to locate .vendor/upx-src/src/stub/amd64-linux.elf-fold.h")


def load_stub_prefix() -> bytes:
    text = find_stub_header().read_text()
    body = text.split("{", 1)[1].rsplit("}", 1)[0]
    values = [int(token) for token in re.findall(r"\b\d+\b", body)]
    return bytes(values[:STUB_PREFIX_LEN])


def find_unique(blob: bytes, pattern: bytes, label: str) -> int:
    offset = blob.find(pattern)
    if offset < 0:
        raise SystemExit(f"{label} signature not found")
    if blob.find(pattern, offset + 1) >= 0:
        raise SystemExit(f"{label} signature is not unique")
    return offset


def patch(upx_in: Path, upx_out: Path) -> int:
    blob = bytearray(upx_in.read_bytes())
    stub_base = find_unique(bytes(blob), load_stub_prefix(), "amd64-linux.elf-fold")
    already_patched = True

    for patch_item in PATCHES:
        start = stub_base + patch_item.rel_offset
        end = start + len(patch_item.old)
        chunk = bytes(blob[start:end])
        if chunk == patch_item.old:
            already_patched = False
            continue
        if chunk != patch_item.new:
            raise SystemExit(
                f"incompatible UPX stub contents at 0x{start:x}: "
                f"got {chunk.hex()}, expected {patch_item.old.hex()} or {patch_item.new.hex()}"
            )

    if not already_patched:
        for patch_item in PATCHES:
            start = stub_base + patch_item.rel_offset
            end = start + len(patch_item.new)
            blob[start:end] = patch_item.new

    upx_out.write_bytes(blob)
    os.chmod(upx_out, upx_in.stat().st_mode)
    state = "already patched" if already_patched else "patched"
    print(f"{state} {upx_out} using stub base 0x{stub_base:x}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        raise SystemExit(f"usage: {argv[0]} <upx-binary> <output-upx-binary>")
    return patch(Path(argv[1]), Path(argv[2]))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
