#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from arx_core import DECOY_FLAG, REAL_FLAG


def final_line(text: str) -> str:
    lines = [line for line in text.splitlines() if line]
    return lines[-1] if lines else ""


def run_case(path: Path, candidate: str) -> tuple[int, str]:
    completed = subprocess.run(
        [str(path), candidate],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode, final_line(completed.stdout)


def expect(path: Path, accept: str, reject: str) -> None:
    code, output = run_case(path, accept)
    if code != 0 or output != "correct!":
        raise SystemExit(f"{path.name} should accept {accept!r}, got code={code}, output={output!r}")

    code, output = run_case(path, reject)
    if code == 0 or output != "try again~":
        raise SystemExit(f"{path.name} should reject {reject!r}, got code={code}, output={output!r}")


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    dist = root / "dist"

    plain = dist / "GQuuuuuupX"
    packed = dist / "GQuuuuuupX-packed"
    unpacked = dist / "GQuuuuuupX-unpacked"

    print(f"decoy: {DECOY_FLAG}")
    print(f"real : {REAL_FLAG}")

    expect(plain, DECOY_FLAG, REAL_FLAG)
    expect(unpacked, DECOY_FLAG, REAL_FLAG)
    expect(packed, REAL_FLAG, DECOY_FLAG)

    print("verification: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
