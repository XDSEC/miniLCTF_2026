#!/usr/bin/env python3
"""Generate Wabun code (和文モールス符号) audio encoded with bird sounds.

Three bird sounds are used:
  - bird 0 (0.wav): dot  (・) — short chirp
  - bird 1 (1.wav): dash (ー) — double chirp
  - bird 2 (2.wav): character separator

Usage:
  python generate.py "フラグハト" -o challenge.wav
  python generate.py "コンニチハ" -o output.wav --gap 80 --sep-gap 250
"""

import argparse
import sys
import wave
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
BIRD_DIR = SCRIPT_DIR / "bird_sounds"

BIRD_DOT = BIRD_DIR / "0.wav"
BIRD_DASH = BIRD_DIR / "1.wav"
BIRD_SEP = BIRD_DIR / "2.wav"

# ── Complete Wabun code table (standard Japanese Morse) ──────────────────

WABUN = {
    # ア行
    "ア": "--.--", "イ": ".-", "ウ": "..-", "エ": "-.---", "オ": ".-...",
    # カ行
    "カ": ".-..", "キ": "-.-..", "ク": "...-", "ケ": "-.--", "コ": "----",
    # サ行
    "サ": "-.-.-", "シ": "--.-.", "ス": "---.-", "セ": ".---.", "ソ": "---.",
    # タ行
    "タ": "-.", "チ": "..-.", "ツ": ".--.", "テ": ".-.--", "ト": "..-..",
    # ナ行
    "ナ": ".-.", "ニ": "-.-.", "ヌ": "....", "ネ": "--.-", "ノ": "..--",
    # ハ行
    "ハ": "-...", "ヒ": "--..-", "フ": "--..", "ヘ": ".", "ホ": "-..",
    # マ行
    "マ": "-..-", "ミ": "..-.-", "ム": "-", "メ": "-...-", "モ": "-..-.",
    # ヤ行
    "ヤ": ".--", "ユ": "-..--", "ヨ": "--",
    # ラ行
    "ラ": "...", "リ": "--.", "ル": "-.--.", "レ": "---", "ロ": ".-.-",
    # ワ行 + ン
    "ワ": "-.-", "ヰ": ".-..-", "ヱ": ".--..", "ヲ": ".---", "ン": ".-.-.",
    # 記号
    "゛": "..",       # 濁点 (dakuten)
    "゜": "..--.",     # 半濁点 (handakuten)
    "ー": ".--.-",     # 長音 (chōonpu)
    "、": ".-.-.-",    # 読点 (comma)
    "。": ".-.-..",    # 句点 (period)
    "（": "-.--.-",    # 左括弧
    "）": ".-..-.",    # 右括弧
}

# Dakuten/handakuten base mapping for composite kana
_DAKUTEN_BASE = {
    "ガ": "カ", "ギ": "キ", "グ": "ク", "ゲ": "ケ", "ゴ": "コ",
    "ザ": "サ", "ジ": "シ", "ズ": "ス", "ゼ": "セ", "ゾ": "ソ",
    "ダ": "タ", "ヂ": "チ", "ヅ": "ツ", "デ": "テ", "ド": "ト",
    "バ": "ハ", "ビ": "ヒ", "ブ": "フ", "ベ": "ヘ", "ボ": "ホ",
}
_HANDAKUTEN_BASE = {
    "パ": "ハ", "ピ": "ヒ", "プ": "フ", "ペ": "ヘ", "ポ": "ホ",
}


def encode_char(ch: str) -> str:
    """Return dot/dash Morse pattern for a single Japanese character.

    Dakuten / handakuten composites are resolved: base kana pattern
    followed by the modifier pattern with a single signal gap (space).
    """
    if ch in (" ", "　"):  # skip spaces in Japanese text
        return ""
    if ch in WABUN:
        return WABUN[ch]
    if ch in _DAKUTEN_BASE:
        return WABUN[_DAKUTEN_BASE[ch]] + " " + WABUN["゛"]
    if ch in _HANDAKUTEN_BASE:
        return WABUN[_HANDAKUTEN_BASE[ch]] + " " + WABUN["゜"]
    raise ValueError(f"Unknown character: {ch!r}")


def encode_text(text: str) -> list[str]:
    """Convert Japanese text to a list of Morse patterns, one per character."""
    result: list[str] = []
    for ch in text:
        pat = encode_char(ch)
        if pat:
            result.append(pat)
    return result


# ── International Morse code ─────────────────────────────────────────────

MORSE: dict[str, str] = {
    # Letters
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".",
    "F": "..-.", "G": "--.", "H": "....", "I": "..", "J": ".---",
    "K": "-.-", "L": ".-..", "M": "--", "N": "-.", "O": "---",
    "P": ".--.", "Q": "--.-", "R": ".-.", "S": "...", "T": "-",
    "U": "..-", "V": "...-", "W": ".--", "X": "-..-", "Y": "-.--",
    "Z": "--..",
    # Digits
    "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-",
    "5": ".....", "6": "-....", "7": "--...", "8": "---..", "9": "----.",
    # Punctuation
    ".": ".-.-.-", ",": "--..--", "?": "..--..", "'": ".----.",
    "!": "-.-.--", "/": "-..-.", "(": "-.--.", ")": "-.--.-",
    "&": ".-...", ":": "---...", ";": "-.-.-.", "=": "-...-",
    "+": ".-.-.", "-": "-....-", "_": "..--.-", '"': ".-..-.",
    "$": "...-..-", "@": ".--.-.",
}


def encode_latin(text: str) -> str:
    """Convert ASCII text to dot/dash Morse pattern.

    Letters/digits separated by single space (signal gap).
    Actual space -> two spaces (longer gap for word boundary).
    """
    result: list[str] = []
    for ch in text:
        if ch == " ":
            result.append(" ")  # word boundary
        else:
            upper = ch.upper()
            if upper not in MORSE:
                raise ValueError(f"Unknown Latin character: {ch!r}")
            result.append(MORSE[upper])
    return "  ".join(result)


# ── Kana normalization ──────────────────────────────────────────────────

# Small kana → full-size for Wabun encoding
_SMALL_KANA = str.maketrans({
    "ァ": "ア", "ィ": "イ", "ゥ": "ウ", "ェ": "エ", "ォ": "オ",
    "ッ": "ツ", "ャ": "ヤ", "ュ": "ユ", "ョ": "ヨ",
    "ヵ": "カ", "ヶ": "ケ",
})


def normalize_kana(text: str) -> str:
    """Convert small kana to full-size so Wabun table can look them up."""
    return text.translate(_SMALL_KANA)


# ── Prosigns ─────────────────────────────────────────────────────────────

# Prosigns split into individual letters so the separator bird (bird2)
# appears between D/O and S/N, helping players recognise them.
DO_PARTS = ["-..", "---"]  # D then O
SN_PARTS = ["...", "-."]   # S then N


# ── WAV I/O ──────────────────────────────────────────────────────────────

WavParams = tuple[int, int, int]  # (nchannels, sampwidth, framerate)


def read_wav(path: Path) -> tuple[WavParams, bytes]:
    """Read a WAV file, return ((nchannels, sampwidth, framerate), frames_bytes)."""
    with wave.open(str(path), "rb") as w:
        params = (w.getnchannels(), w.getsampwidth(), w.getframerate())
        frames = w.readframes(w.getnframes())
    return params, frames


def make_silence(params: WavParams, duration_ms: int) -> bytes:
    """Return raw bytes of silence matching sample width × channels × duration."""
    nchannels, sampwidth, framerate = params
    nframes = int(framerate * duration_ms / 1000)
    return b"\x00" * (nframes * nchannels * sampwidth)


def _parse_segments(text: str) -> list[tuple[str, str]]:
    """Split text into ('ja'|'en', content) segments on [...] markers."""
    segments: list[tuple[str, str]] = []
    buf: list[str] = []
    mode = "ja"
    for ch in text:
        if ch == "[":
            if buf:
                segments.append((mode, "".join(buf)))
                buf.clear()
            mode = "en"
        elif ch == "]":
            if buf:
                segments.append((mode, "".join(buf)))
                buf.clear()
            mode = "ja"
        else:
            buf.append(ch)
    if buf:
        segments.append((mode, "".join(buf)))
    return segments


def build_audio(
    text: str,
    gap_ms: int = 100,
    sep_gap_ms: int = 300,
    add_do: bool = True,
    add_sn: bool = True,
) -> tuple[WavParams, bytes]:
    """Build the full encoded audio. Returns (wav_params, raw_data_bytes).

    Japanese text may contain [...] blocks that are sent as international
    Morse.  Mode switches insert DO / SN prosigns automatically.
    """

    # Load bird sounds
    params_dot, frames_dot = read_wav(BIRD_DOT)
    params_dash, frames_dash = read_wav(BIRD_DASH)
    params_sep, frames_sep = read_wav(BIRD_SEP)

    assert params_dash == params_dot, "Bird WAV formats differ"
    assert params_sep == params_dot, "Bird WAV formats differ"
    params = params_dot

    gap = make_silence(params, gap_ms)
    sep_gap = make_silence(params, sep_gap_ms)
    word_gap = make_silence(params, max(800, sep_gap_ms * 5))  # min 800 ms word gap

    segments = _parse_segments(text)

    # Build flat list of Morse patterns, with prosigns at mode switches
    patterns: list[str] = []  # each entry is a dot/dash pattern; "" = word gap

    first_mode = segments[0][0] if segments else "ja"
    if add_do and first_mode == "ja":
        patterns.extend(DO_PARTS)

    prev_mode = first_mode
    for seg_mode, seg_text in segments:
        if seg_mode != prev_mode:
            # Mode switch: ja→en inserts SN, en→ja inserts DO
            patterns.extend(SN_PARTS if seg_mode == "en" else DO_PARTS)

        if seg_mode == "ja":
            patterns.extend(encode_text(seg_text))
        else:
            words = seg_text.split(" ")
            for wi, word in enumerate(words):
                for ch in word:
                    upper = ch.upper()
                    if upper not in MORSE:
                        raise ValueError(f"Unknown Latin character: {ch!r}")
                    patterns.append(MORSE[upper])
                if wi < len(words) - 1:
                    patterns.append("")  # word-boundary marker

        prev_mode = seg_mode

    if add_sn and prev_mode == "ja":
        patterns.extend(SN_PARTS)

    # Render patterns into audio chunks
    chunks: list[bytes] = []

    for i, pattern in enumerate(patterns):
        if pattern == "":
            chunks.append(word_gap)
            continue

        # Encode one Morse pattern (may contain space for dakuten)
        parts = pattern.split(" ")
        for pi, part in enumerate(parts):
            for symbol in part:
                if symbol == ".":
                    chunks.append(frames_dot)
                elif symbol == "-":
                    chunks.append(frames_dash)
                else:
                    raise ValueError(f"Unexpected symbol {symbol!r}")
                chunks.append(gap)
            if pi < len(parts) - 1:
                chunks.append(gap)

        # Character separator (bird 2), skip after last pattern or before word gap
        if i < len(patterns) - 1 and patterns[i + 1] != "":
            chunks.append(sep_gap)
            chunks.append(frames_sep)
            chunks.append(sep_gap)

    return params, b"".join(chunks)


def write_wav(path: str, params: WavParams, data: bytes) -> None:
    """Write audio data as a WAV file."""
    nchannels, sampwidth, framerate = params
    with wave.open(path, "wb") as w:
        w.setnchannels(nchannels)
        w.setsampwidth(sampwidth)
        w.setframerate(framerate)
        w.writeframes(data)


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Encode Japanese text as bird-call Wabun code audio"
    )
    parser.add_argument(
        "text",
        help="Japanese text to encode (e.g. フラグハト)",
    )
    parser.add_argument(
        "-o", "--output",
        default="output.wav",
        help="Output WAV file path (default: output.wav)",
    )
    parser.add_argument(
        "--gap",
        type=int,
        default=100,
        help="Signal gap in ms between dots/dashes (default: 100)",
    )
    parser.add_argument(
        "--sep-gap",
        type=int,
        default=300,
        help="Silence padding around separator bird call in ms (default: 300)",
    )
    parser.add_argument(
        "--no-do",
        action="store_true",
        help="Omit DO (start-of-Wabun) prosign",
    )
    parser.add_argument(
        "--no-sn",
        action="store_true",
        help="Omit SN (end-of-Wabun) prosign",
    )
    args = parser.parse_args()

    text = normalize_kana(args.text.strip())
    if not text:
        print("Error: empty input text", file=sys.stderr)
        sys.exit(1)

    # Show the encoding for verification
    print("Morse encoding:")
    segments = _parse_segments(text)
    first_mode = segments[0][0] if segments else "ja"
    out = ''
    if not args.no_do and first_mode == "ja":
        print(f"  [DO]  D → {DO_PARTS[0]}  |  O → {DO_PARTS[1]}")
        out += DO_PARTS[0] + ' '
        out += DO_PARTS[1] + ' '
    prev_mode = first_mode
    for seg_mode, seg_text in segments:
        if seg_mode != prev_mode:
            if seg_mode == "en":
                print(f"  [SN]  S → {SN_PARTS[0]}  |  N → {SN_PARTS[1]}")
                out += SN_PARTS[0] + ' '
                out += SN_PARTS[1] + ' '
            else:
                print(f"  [DO]  D → {DO_PARTS[0]}  |  O → {DO_PARTS[1]}")
                out += DO_PARTS[0] + ' '
                out += DO_PARTS[1] + ' '
        if seg_mode == "ja":
            for ch in seg_text:
                pat = encode_char(ch)
                print(f"  {ch}  →  {pat}")
                out += pat + ' '
        else:
            print(f"  ── English ──")
            for ch in seg_text:
                upper = ch.upper()
                if upper in MORSE:
                    print(f"  {ch}  →  {MORSE[upper]}")
                    out += MORSE[upper] + ' '
                elif ch == " ":
                    print(f"  [space]")
                    out += ' '
                else:
                    print(f" [!!!!!!!!!!!!!!!!!!!!!!!!!!] error")
        prev_mode = seg_mode
    if not args.no_sn and prev_mode == "ja":
        print(f"  [SN]  S → {SN_PARTS[0]}  |  N → {SN_PARTS[1]}")
        out += SN_PARTS[0] + ' '
        out += SN_PARTS[1] + ' '
    print(f"{out =}")

    # Build audio
    params, audio_data = build_audio(
        text,
        gap_ms=args.gap,
        sep_gap_ms=args.sep_gap,
        add_do=not args.no_do,
        add_sn=not args.no_sn,
    )
    write_wav(args.output, params, audio_data)

    nchannels, sampwidth, framerate = params
    duration_s = len(audio_data) / (nchannels * sampwidth * framerate)
    print(f"\nWrote {args.output}  ({duration_s:.1f} s)")


if __name__ == "__main__":
    main()
