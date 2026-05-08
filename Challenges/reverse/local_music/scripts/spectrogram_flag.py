#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "mutagen>=1.47",
#   "numpy>=2.2",
#   "pillow>=11.0",
#   "scipy>=1.15",
# ]
# ///

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.io import wavfile
from scipy.signal import istft, stft
from mutagen.id3 import ID3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render text into a spectrogram-shaped audio layer and mix it into a track."
    )
    parser.add_argument("input", type=Path, help="input audio file, e.g. flag.flac")
    parser.add_argument("output", type=Path, help="output audio file")
    parser.add_argument("text", help="text to draw in the spectrogram")
    parser.add_argument(
        "--start",
        type=float,
        help="start time in seconds; default is a later segment near the end",
    )
    parser.add_argument("--duration", type=float, default=20.0, help="draw duration in seconds")
    parser.add_argument("--sample-rate", type=int, default=48_000, help="working sample rate")
    parser.add_argument("--low-freq", type=float, default=1_200.0, help="bottom frequency in Hz")
    parser.add_argument("--high-freq", type=float, default=13_000.0, help="top frequency in Hz")
    parser.add_argument("--nfft", type=int, default=4_096, help="STFT size")
    parser.add_argument("--hop", type=int, default=256, help="STFT hop size")
    parser.add_argument("--height", type=int, default=820, help="image height in pixels")
    parser.add_argument("--font-size", type=int, default=320, help="text font size")
    parser.add_argument("--font", type=Path, help="optional .ttf/.otf font path")
    parser.add_argument(
        "--cut-db",
        type=float,
        default=32.0,
        help="legacy option; hard-cut mode now removes the masked bins completely",
    )
    parser.add_argument(
        "--bright",
        type=float,
        default=2.2,
        help="spectrogram brightness multiplier",
    )
    parser.add_argument(
        "--preview",
        type=Path,
        help="optional path to save the rendered text image",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_ffmpeg()

    samples = read_audio(args.input, args.sample_rate)
    if args.start is None:
        args.start = default_start(samples.shape[0] / args.sample_rate, args.duration)
    image = render_text_image(args)
    if args.preview:
        image.save(args.preview)

    stamped = stamp_spectrogram(samples, image, args)
    write_audio(args.input, args.output, stamped, args.sample_rate)


def ensure_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg not found in PATH")


def read_audio(path: Path, sample_rate: int) -> np.ndarray:
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(path),
        "-ar",
        str(sample_rate),
        "-ac",
        "2",
        "-f",
        "f32le",
        "-",
    ]
    proc = subprocess.run(cmd, check=True, capture_output=True)
    audio = np.frombuffer(proc.stdout, dtype=np.float32)
    if audio.size == 0:
        raise SystemExit("decoded audio is empty")
    return audio.reshape(-1, 2).copy()


def write_audio(source_path: Path, output_path: Path, audio: np.ndarray, sample_rate: int) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmpdir:
        wav_path = Path(tmpdir) / "spectrogram_flag.wav"
        audio_path = Path(tmpdir) / f"audio{output_path.suffix.lower() or '.bin'}"
        wavfile.write(wav_path, sample_rate, np.clip(audio, -1.0, 1.0).astype(np.float32))

        encode_cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(wav_path)]
        if output_path.suffix.lower() == ".mp3":
            encode_cmd += ["-c:a", "libmp3lame", "-b:a", "320k"]
        elif output_path.suffix.lower() == ".flac":
            encode_cmd += ["-c:a", "flac"]
        encode_cmd.append(str(audio_path))
        subprocess.run(encode_cmd, check=True)

        if output_path.suffix.lower() == ".mp3":
            copy_mp3_tags(source_path, audio_path)
            audio_path.replace(output_path)
            return

        mux_cmd = [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            str(audio_path),
            "-i",
            str(source_path),
            "-map",
            "0:a",
            "-map",
            "1:v?",
            "-map_metadata",
            "1",
        ]
        if output_path.suffix.lower() == ".mp3":
            mux_cmd += ["-c:a", "copy", "-c:v", "copy"]
        elif output_path.suffix.lower() == ".flac":
            mux_cmd += ["-c:a", "copy", "-c:v", "copy"]
        mux_cmd.append(str(output_path))
        subprocess.run(mux_cmd, check=True)


def copy_mp3_tags(source_path: Path, target_path: Path) -> None:
    ID3(str(source_path)).save(str(target_path), v2_version=4)


def render_text_image(args: argparse.Namespace) -> Image.Image:
    width = max(64, int(args.duration * args.sample_rate / args.hop))
    canvas = Image.new("L", (width, args.height), 0)
    draw = ImageDraw.Draw(canvas)
    text = layout_text(args.text)
    font = load_font(args)
    bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=14, stroke_width=1)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    scale = min((width * 0.96) / max(text_w, 1), (args.height * 0.86) / max(text_h, 1))
    if scale < 1.0:
        font = load_font(args, size=max(12, int(args.font_size * scale)))
        bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=14, stroke_width=1)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

    x = (width - text_w) / 2 - bbox[0]
    y = (args.height - text_h) / 2 - bbox[1]
    draw.multiline_text(
        (x, y),
        text,
        fill=255,
        font=font,
        spacing=14,
        align="center",
        stroke_width=1,
        stroke_fill=255,
    )

    image = canvas.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    return image


def load_font(args: argparse.Namespace, size: int | None = None) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    size = size or args.font_size
    if args.font:
        return ImageFont.truetype(str(args.font), size=size)

    for candidate in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansMonoCJK-Regular.ttc",
    ]:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)

    return ImageFont.load_default()


def layout_text(text: str) -> str:
    if len(text) <= 22:
        return text
    if "{" in text and text.endswith("}"):
        left, right = text.split("{", 1)
        right = right[:-1]
        pivot = len(right) // 2
        cut = min(
            (i for i in range(max(1, pivot - 6), min(len(right), pivot + 7)) if right[i] == "-"),
            key=lambda i: abs(i - pivot),
            default=pivot,
        )
        return f"{left}{{{right[:cut+1]}\n{right[cut+1:]}}}"
    pivot = len(text) // 2
    return f"{text[:pivot]}\n{text[pivot:]}"


def stamp_spectrogram(base: np.ndarray, image: Image.Image, args: argparse.Namespace) -> np.ndarray:
    pixels = np.asarray(image, dtype=np.float32) / 255.0
    pixels = np.power(np.clip(pixels, 0.0, 1.0), 0.72) * args.bright
    pixels = np.clip(pixels, 0.0, 1.0)
    pixels = (pixels > 0.28).astype(np.float32)

    nfft = args.nfft
    hop = args.hop
    sample_rate = args.sample_rate
    noverlap = nfft - hop
    start_frame = int(round(args.start * sample_rate / hop))
    width = pixels.shape[1]
    low_bin = hz_to_bin(args.low_freq, sample_rate, nfft)
    high_bin = hz_to_bin(args.high_freq, sample_rate, nfft)
    row_bins = np.linspace(low_bin, high_bin, pixels.shape[0]).astype(int)
    out = np.zeros_like(base)
    for channel in range(base.shape[1]):
        original = base[:, channel]
        _, _, spec = stft(
            original,
            fs=sample_rate,
            window="hann",
            nperseg=nfft,
            noverlap=noverlap,
            boundary="zeros",
            padded=True,
        )
        if start_frame + width >= spec.shape[1]:
            extra = start_frame + width - spec.shape[1] + 1
            spec = np.pad(spec, ((0, 0), (0, extra)))

        mag = np.abs(spec)
        phase = np.exp(1j * np.angle(spec))
        gain_map = np.ones_like(mag, dtype=np.float32)

        for x in range(width):
            frame = start_frame + x
            for row, bin_index in enumerate(row_bins):
                mask = pixels[row, x]
                if mask < 0.05:
                    continue
                stamp_gain(gain_map, bin_index, frame, mask)

        stamped = (mag * gain_map) * phase
        _, signal = istft(
            stamped,
            fs=sample_rate,
            window="hann",
            nperseg=nfft,
            noverlap=noverlap,
            input_onesided=True,
            boundary=True,
        )
        out[:, channel] = fit_length(signal.astype(np.float32), base.shape[0])

    peak = np.max(np.abs(out))
    if peak > 1.0:
        out /= peak * 1.02
    return out


def fit_length(signal: np.ndarray, target_len: int) -> np.ndarray:
    if signal.size >= target_len:
        return signal[:target_len]
    return np.pad(signal, (0, target_len - signal.size))


def stamp_gain(gain_map: np.ndarray, bin_index: int, frame: int, mask: float) -> None:
    for frame_delta, frame_weight in [(-1, 0.45), (0, 1.0), (1, 0.45)]:
        frame_idx = frame + frame_delta
        if not 0 <= frame_idx < gain_map.shape[1]:
            continue
        for bin_delta, bin_weight in [(-2, 0.18), (-1, 0.5), (0, 1.0), (1, 0.5), (2, 0.18)]:
            bin_idx = bin_index + bin_delta
            if 0 <= bin_idx < gain_map.shape[0]:
                strength = mask * frame_weight * bin_weight
                local_gain = 0.0 if strength >= 0.18 else 1.0 - strength / 0.18
                gain_map[bin_idx, frame_idx] = min(gain_map[bin_idx, frame_idx], local_gain)


def hz_to_bin(freq: float, sample_rate: int, nfft: int) -> int:
    return max(1, min(int(round(freq * nfft / sample_rate)), nfft // 2))


def default_start(total_duration: float, draw_duration: float) -> float:
    return max(0.0, total_duration - draw_duration - 18.0)


if __name__ == "__main__":
    main()
