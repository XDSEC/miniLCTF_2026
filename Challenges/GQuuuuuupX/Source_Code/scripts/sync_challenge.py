#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

from arx_core import BODY_ALPHABET, BODY_LEN, DECOY_FLAG, MATERIAL_BLOB, REAL_FLAG


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
MAIN_C = ROOT / "src" / "main.c"
METADATA = PROJECT_ROOT / "metadata.yml"
AUTHOR = PROJECT_ROOT / "AUTHOR.md"


def format_u8_array(name: str, size_expr: str, data: bytes, per_line: int = 8) -> str:
    lines = [f"static const uint8_t {name}[{size_expr}] = {{"]
    for base in range(0, len(data), per_line):
        chunk = ", ".join(f"0x{value:02X}" for value in data[base : base + per_line])
        suffix = "," if base + per_line < len(data) else ""
        lines.append(f"    {chunk}{suffix}")
    lines.append("};")
    return "\n".join(lines)


def format_allowed_table(alphabet: str) -> str:
    table = bytearray(128)
    for ch in alphabet:
        code = ord(ch)
        if code >= 128:
            raise ValueError("BODY_ALPHABET must stay ASCII")
        table[code] = 1
    return format_u8_array("g_body_allowed", "128", bytes(table), per_line=16)


def replace_once(text: str, pattern: str, replacement: str, *, flags: int = 0, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise SystemExit(f"unable to update {label}")
    return updated


def sync_main_c() -> None:
    text = MAIN_C.read_text()
    text = replace_once(text, r"^#define BODY_LEN \d+u$", f"#define BODY_LEN {BODY_LEN}u", flags=re.M, label="BODY_LEN")
    text = replace_once(
        text,
        r"static const uint8_t g_material_blob\[[^\]]+\] = \{\n.*?\n\};",
        format_u8_array("g_material_blob", "MATERIAL_BLOB_SIZE", MATERIAL_BLOB),
        flags=re.S,
        label="g_material_blob",
    )
    if "static const uint8_t g_body_allowed[128]" not in text:
        marker = "static int legal_body(const unsigned char *body) {"
        placeholder = format_u8_array("g_body_allowed", "128", bytes(128)) + "\n\n"
        if marker not in text:
            raise SystemExit("unable to insert g_body_allowed")
        text = text.replace(marker, placeholder + marker, 1)
    text = replace_once(
        text,
        r"static const uint8_t g_body_allowed\[128\] = \{\n.*?\n\};",
        format_allowed_table(BODY_ALPHABET),
        flags=re.S,
        label="g_body_allowed",
    )
    MAIN_C.write_text(text)


def sync_metadata() -> None:
    text = METADATA.read_text()
    text = replace_once(text, r"^flag: .*$", f"flag: {REAL_FLAG}", flags=re.M, label="metadata flag")
    METADATA.write_text(text)


def sync_author() -> None:
    text = AUTHOR.read_text()
    text = replace_once(text, r"^Flag: `.*`$", f"Flag: `{REAL_FLAG}`", flags=re.M, label="author flag")
    text = replace_once(text, r"^Decoy: `.*`$", f"Decoy: `{DECOY_FLAG}`", flags=re.M, label="author decoy")
    AUTHOR.write_text(text)


def main() -> int:
    sync_main_c()
    sync_metadata()
    sync_author()
    print(f"synced BODY_LEN={BODY_LEN}, real={REAL_FLAG}, decoy={DECOY_FLAG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
