#!/usr/bin/env python3
from __future__ import annotations

import argparse

from arx_core import (
    DECOY_BODY,
    DECOY_KEY,
    MATERIAL_BLOB,
    REAL_BODY,
    REAL_KEY,
    BODY_LEN,
    build_material_words,
    encode_material_bytes,
    recover_body,
)


def print_c_array(blob: bytes) -> None:
    print(f"static const uint8_t g_material_blob[{len(blob)}] = {{")
    for index, byte_value in enumerate(blob):
        end = "," if index != len(blob) - 1 else ""
        prefix = "    " if index % 8 == 0 else ""
        suffix = "\n" if index % 8 == 7 else " "
        print(f"{prefix}0x{byte_value:02X}{end}", end=suffix)
    if len(blob) % 8:
        print()
    print("};")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate or recover GQuuuuuupX verifier material")
    parser.add_argument("--decoy", default=DECOY_BODY, help=f"decoy flag body ({BODY_LEN} bytes)")
    parser.add_argument("--real", default=REAL_BODY, help=f"real flag body ({BODY_LEN} bytes)")
    parser.add_argument("--c-array", action="store_true", help="print the encoded C material blob")
    parser.add_argument("--recover", action="store_true", help="recover bodies from the embedded material blob")
    args = parser.parse_args()

    if args.c_array:
        blob = encode_material_bytes(build_material_words(args.decoy, args.real))
        print_c_array(blob)
        return 0

    if args.recover:
        print(f"decoy: {recover_body(0, DECOY_KEY, MATERIAL_BLOB)}")
        print(f"real : {recover_body(1, REAL_KEY, MATERIAL_BLOB)}")
        return 0

    blob = encode_material_bytes(build_material_words(args.decoy, args.real))
    print(f"embedded blob matches: {blob == MATERIAL_BLOB}")
    print(f"decoy recovered: {recover_body(0, DECOY_KEY, blob)}")
    print(f"real recovered : {recover_body(1, REAL_KEY, blob)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
