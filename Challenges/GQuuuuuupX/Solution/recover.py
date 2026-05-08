#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Source_Code" / "scripts"))

from arx_core import DECOY_FLAG, REAL_FLAG, detect_runtime_key, recover_body, DECOY_KEY, REAL_KEY


def final_line(text: str) -> str:
    lines = [line for line in text.splitlines() if line]
    return lines[-1] if lines else ""


def probe_flag(binary_path: Path, candidate: str) -> bool:
    completed = subprocess.run(
        [str(binary_path), candidate],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0 and final_line(completed.stdout) == "correct!"


def main() -> int:
    handout = ROOT / "Handout" / "GQuuuuuupX"
    hinted_key = detect_runtime_key(handout)
    decoy = recover_body(0, DECOY_KEY)
    real = recover_body(1, REAL_KEY)
    if probe_flag(handout, REAL_FLAG):
        runtime_key = REAL_KEY
        active = REAL_FLAG
    elif probe_flag(handout, DECOY_FLAG):
        runtime_key = DECOY_KEY
        active = DECOY_FLAG
    else:
        raise SystemExit("handout rejected both recovered flags")

    print(f"stub hint   : {f'0x{hinted_key:02x}' if hinted_key is not None else 'not found in packed blob'}")
    print(f"handout key : 0x{runtime_key:02x}")
    print(f"decoy body  : {decoy}")
    print(f"real body   : {real}")
    print(f"decoy flag  : {DECOY_FLAG}")
    print(f"real flag   : {REAL_FLAG}")
    print(f"active flag : {active}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
