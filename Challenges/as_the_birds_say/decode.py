#!/usr/bin/env python3
"""Decode bird-call Wabun code → Morse code (sequential greedy).

Treat the audio as a sequence of three known "letters" (dot/dash/sep),
each with a precisely known duration.  At each position, compare the
audio segment against the three MP3-roundtripped templates and pick
the best match.  Advance by the winner's length.  That's it.

Usage
-----
  uv run --with numpy decode.py challenge.mp3
  uv run --with numpy decode.py challenge.mp3 --threshold 0.3 --compact
"""

import argparse, io, os, subprocess, sys, tempfile, wave
from pathlib import Path
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
BIRD_DIR = SCRIPT_DIR / "bird_sounds"
BIRD_PATHS = [BIRD_DIR / "0.wav", BIRD_DIR / "1.wav", BIRD_DIR / "2.wav"]
SR = 11025


def load(path: Path) -> np.ndarray:
    cmd = ["ffmpeg", "-i", str(path), "-f", "wav", "-acodec", "pcm_s16le",
           "-ac", "1", "-ar", str(SR), "-loglevel", "error", "pipe:1"]
    proc = subprocess.run(cmd, capture_output=True, check=True)
    buf = io.BytesIO(proc.stdout)
    with wave.open(buf, "rb") as w:
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32)


def mp3rt(wav: Path) -> np.ndarray:
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as t:
        tmp = t.name
    subprocess.run(["ffmpeg", "-i", str(wav), "-codec:a", "libmp3lame",
                    "-b:a", "128k", "-loglevel", "error", "-y", tmp], check=True)
    d = load(Path(tmp)); os.unlink(tmp); return d


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def decode(audio: np.ndarray, tmpls: list[np.ndarray],
           threshold: float = 0.3) -> list[tuple[float, int]]:
    """Greedy sequential decoder.  Label -1 = word gap.

    After each pick, the pointer advances by the template's exact length
    plus a small local refinement (search ±50 samples for best alignment).
    """
    lens = [len(t) for t in tmpls]
    n = len(audio)
    pos = 0
    events: list[tuple[float, int]] = []
    search = 50  # local refinement window (samples)

    while pos + min(lens) <= n:
        # Try each template at current position + small local shifts
        best_score, best_label, best_shift = -1.0, -1, 0
        for label, (tmpl, L) in enumerate(zip(tmpls, lens)):
            for shift in range(-search, search + 1):
                p = pos + shift
                if p < 0 or p + L > n:
                    continue
                s = cosine(audio[p:p + L], tmpl)
                if s > best_score:
                    best_score, best_label, best_shift = s, label, shift

        if best_score < threshold:
            # silence → word gap
            if events and events[-1][1] != -1:
                events.append((pos / SR, -1))
            pos += int(0.1 * SR)
        else:
            actual_pos = pos + best_shift
            events.append((actual_pos / SR, best_label))
            pos = actual_pos + lens[best_label]

    return events


def to_morse(events: list[tuple[float, int]]) -> str:
    p = []
    for _, l in events:
        if l == 0: p.append(".")
        elif l == 1: p.append("-")
        elif l == 2: p.append("|")
        elif l == -1: p.append("  ")
    return " ".join("".join(p).split())


def main():
    p = argparse.ArgumentParser(description="Decode bird-call Wabun → Morse")
    p.add_argument("audio"); p.add_argument("--threshold", type=float, default=0.3)
    p.add_argument("--compact", action="store_true"); p.add_argument("--raw", action="store_true")
    args = p.parse_args()

    ap = Path(args.audio)
    if not ap.exists(): print("file not found", file=sys.stderr); sys.exit(1)

    print(f"Loading ({ap.suffix})…", file=sys.stderr)
    audio = load(ap)
    print(f"  {len(audio)/SR:.1f}s {len(audio)}samples", file=sys.stderr)

    print("Loading templates (MP3-roundtripped)…", file=sys.stderr)
    tmpls = []
    for bp in BIRD_PATHS:
        t = mp3rt(bp)
        tmpls.append(t)
        print(f"  {bp.name}: {len(t)}samples ({len(t)/SR:.3f}s)", file=sys.stderr)

    print(f"Decoding (threshold={args.threshold})…", file=sys.stderr)
    events = decode(audio, tmpls, args.threshold)

    c = {0: 0, 1: 0, 2: 0, -1: 0}
    for _, l in events: c[l] = c.get(l, 0) + 1
    print(f"  {len(events)} events dot={c[0]} dash={c[1]} sep={c[2]} gaps={c[-1]}",
          file=sys.stderr)

    if args.raw:
        for t, l in events:
            print(f"{t:9.3f}s  {['dot','dash','sep','gap'][l]}")
        return

    morse = to_morse(events)
    if args.compact: print(morse)
    else:
        print(f"\n=== Morse ({len(events)} events) ===\n")
        for i in range(0, len(morse), 120): print(morse[i:i+120])


if __name__ == "__main__":
    main()
