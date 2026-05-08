#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


HEADER = b"MINILCTF\x00\x00"
KEY_PREFIX = b"miniL-audio-key"
META_PREFIX = b"miniL:"
COMMENT_PREFIX = b"miniL meta:"
KEY_SEED_PREFIX = b"KaguyaIrohaYachiyo"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Decrypt a wyy challenge container back into audio using file mtime."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="dist/flag.enc",
        type=Path,
        help="encrypted container path",
    )
    parser.add_argument(
        "--timestamp",
        type=int,
        help="override timestamp in unix seconds instead of reading file mtime",
    )
    parser.add_argument(
        "--search",
        type=int,
        default=10000,
        help="search this many seconds around the base timestamp",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="directory for extracted files; default is next to input",
    )
    parser.add_argument(
        "--stem",
        help="output stem; default is input stem",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if shutil.which("openssl") is None:
        raise SystemExit("openssl not found in PATH")
    data = args.input.read_bytes()
    if not data.startswith(HEADER):
        raise SystemExit("bad container header")

    base_ts = args.timestamp or int(args.input.stat().st_mtime)
    ts, audio, meta, image = try_decrypt_nearby(data, base_ts, max(args.search, 0))

    out_dir = args.output_dir or args.input.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.stem or args.input.stem

    meta_json = decode_metadata(meta)
    audio_ext = detect_audio_ext(audio)
    audio_path = out_dir / f"{stem}.{audio_ext}"
    audio_path.write_bytes(audio)

    meta_path = out_dir / f"{stem}.json"
    meta_path.write_text(json.dumps(meta_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    image_path = None
    if image:
        image_ext = detect_image_ext(image)
        image_path = out_dir / f"{stem}.{image_ext}"
        image_path.write_bytes(image)

    print(f"timestamp={ts}")
    print(f"audio={audio_path}")
    print(f"meta={meta_path}")
    if image_path:
        print(f"cover={image_path}")


def try_decrypt_nearby(
    data: bytes, base_ts: int, radius: int
) -> tuple[int, bytes, bytes, bytes]:
    last_error = "unknown error"
    for ts in candidate_timestamps(base_ts, radius):
        try:
            core_key, meta_key = derive_keys(ts)
            audio, meta, image = decrypt_container(data, core_key, meta_key)
            return ts, audio, meta, image
        except SystemExit as exc:
            last_error = str(exc)

    if radius == 0:
        raise SystemExit(last_error)
    raise SystemExit(
        f"failed to decrypt around timestamp {base_ts} (+/-{radius}s): {last_error}"
    )


def candidate_timestamps(base_ts: int, radius: int) -> list[int]:
    order = [base_ts]
    for delta in range(1, radius + 1):
        order.append(base_ts + delta)
        order.append(base_ts - delta)
    return order


def derive_keys(ts: int) -> tuple[bytes, bytes]:
    digest = hashlib.sha256(KEY_SEED_PREFIX + str(ts).encode()).digest()
    return digest[:16], digest[16:]


def decrypt_container(data: bytes, core_key: bytes, meta_key: bytes) -> tuple[bytes, bytes, bytes]:
    pos = len(HEADER)

    key_frame, pos = read_frame(data, pos)
    key_frame = bytes(b ^ 0x64 for b in key_frame)
    audio_key = decrypt_key_frame(key_frame, core_key)

    meta_frame, pos = read_frame(data, pos)
    meta_frame = bytes(b ^ 0x63 for b in meta_frame)
    meta = decrypt_meta_frame(meta_frame, meta_key)

    pos += 5
    image_offset = int.from_bytes(data[pos : pos + 4], "little")
    pos += 4
    image, pos = read_frame(data, pos)
    if image_offset > len(image):
        pos += image_offset - len(image)

    audio = decrypt_audio(data[pos:], audio_key)
    return audio, meta, image


def decrypt_key_frame(key_frame: bytes, core_key: bytes) -> bytes:
    plain = pkcs7_unpad(aes128_ecb_decrypt(key_frame, core_key))
    if not plain.startswith(KEY_PREFIX):
        raise SystemExit("bad decrypted key frame")
    return plain[len(KEY_PREFIX) :]


def decrypt_meta_frame(meta_frame: bytes, meta_key: bytes) -> bytes:
    if not meta_frame.startswith(COMMENT_PREFIX):
        raise SystemExit("bad metadata prefix")
    payload = base64.b64decode(meta_frame[len(COMMENT_PREFIX) :])
    plain = pkcs7_unpad(aes128_ecb_decrypt(payload, meta_key))
    if not plain.startswith(META_PREFIX):
        raise SystemExit("bad decrypted metadata frame")
    return plain[len(META_PREFIX) :]


def decrypt_audio(ciphertext: bytes, key: bytes) -> bytes:
    box = make_key_box(key)
    plain = bytearray(ciphertext)
    for i, value in enumerate(plain):
        j = (i + 1) & 0xFF
        plain[i] = value ^ box[(box[j] + box[(box[j] + j) & 0xFF]) & 0xFF]
    return bytes(plain)


def make_key_box(key: bytes) -> list[int]:
    box = list(range(256))
    last = 0
    for i in range(256):
        last = (box[i] + last + key[i % len(key)]) & 0xFF
        box[i], box[last] = box[last], box[i]
    return box


def read_frame(data: bytes, pos: int) -> tuple[bytes, int]:
    size = int.from_bytes(data[pos : pos + 4], "little")
    pos += 4
    return data[pos : pos + size], pos + size


def aes128_ecb_decrypt(data: bytes, key: bytes) -> bytes:
    proc = subprocess.run(
        [
            "openssl",
            "enc",
            "-aes-128-ecb",
            "-d",
            "-nopad",
            "-nosalt",
            "-K",
            key.hex(),
        ],
        input=data,
        check=True,
        capture_output=True,
    )
    return proc.stdout


def pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        raise SystemExit("empty padded block")
    pad = data[-1]
    if pad == 0 or pad > 16 or data[-pad:] != bytes([pad]) * pad:
        raise SystemExit("bad pkcs7 padding")
    return data[:-pad]


def decode_metadata(meta: bytes) -> dict:
    try:
        return json.loads(meta.decode("utf-8"))
    except Exception:
        return {"raw": meta.decode("utf-8", errors="replace")}


def detect_audio_ext(audio: bytes) -> str:
    if audio.startswith(b"fLaC"):
        return "flac"
    if audio.startswith(b"ID3") or audio[:2] == b"\xFF\xFB":
        return "mp3"
    if audio.startswith(b"OggS"):
        return "ogg"
    if audio[4:12] == b"ftypM4A ":
        return "m4a"
    return "audio"


def detect_image_ext(image: bytes) -> str:
    if image.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if image.startswith(b"\xff\xd8\xff"):
        return "jpg"
    return "bin"


if __name__ == "__main__":
    main()
