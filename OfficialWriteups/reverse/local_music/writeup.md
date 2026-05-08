# local music

## Summary

题目给出一个 `wyy` 二进制文件和 `flag.enc` 加密容器。逆向 `wyy` 发现其将 mp3 音频用 AES-128-ECB + 魔改 RC4 加密打包，密钥由固定字符串与文件修改时间的 SHA256 派生，且合法时间戳范围在编译时固化。爆破时间戳解密得到 mp3 音频后，根据 ID3 标签中的提示 "Do you know FFT?"，查看频谱图即可在末尾段看到 flag。

## Solution

### Step 1: 逆向 wyy，理解加密逻辑

`wyy` 是一个 Rust 编译的二进制，通过 `strings` 和逆向分析可以还原其加密流程：

- **密钥派生**：`SHA256("KaguyaIrohaYachiyo" + timestamp_string)`，前 16 字节为 `core_key`，后 16 字节为 `meta_key`。
- **时间戳约束**：`build.rs` 在编译时将时间戳的合法范围写入 `build_consts.rs`，范围是 `(编译时间/10000) ± 20000` 个桶（每桶 10000 秒）。运行时 `derive_keys()` 内有 `assert!` 保护，超出范围直接 panic。
- **容器结构**：

```
HEADER: 10 字节 "MINILCTF\0\0"
key_frame:  [4 字节 LE 长度] [AES-ECB(KEY_PREFIX + audio_key) ⊕ 0x64]
meta_frame: [4 字节 LE 长度] [COMMENT_PREFIX + base64(AES-ECB(META_PREFIX + json)), 整体逐字节 ⊕ 0x63]
5 字节零填充
image_offset: 4 字节 LE
image_data
audio_data: 与 NcmRc4 流密钥 XOR 加密
```

- **音频加密**：魔改 RC4，KSA 为标准实现，PRGA 的索引计算为 `box[(box[j] + box[(box[j] + j) & 0xFF]) & 0xFF]`。64 字节 audio_key 由 16 字节 core_key 经 4 轮 rotate/add/xor 扩展得到。

### Step 2: 爆破时间戳，解密容器

根据之前的分析，时间戳的范围由 assert 限制，直接枚举时间戳即可。
对于每个候选时间戳：

1. 计算 `SHA256("KaguyaIrohaYachiyo" + ts)` 得到 `core_key` 和 `meta_key`
2. 解析 `key_frame`：逐字节 xor 0x64 后 AES-128-ECB 解密，去掉 `KEY_PREFIX` 得到 `audio_key`
3. 解析 `meta_frame`：逐字节 xor 0x63 后取 `COMMENT_PREFIX` 之后部分 base64 解码，AES-128-ECB 解密得到元数据 JSON
4. 用 `audio_key` 初始化 NcmRc4，XOR 解密音频数据
5. 校验：解密后音频以 `fLaC` 或 `ID3`/`0xFF 0xFB` 开头即为成功

完整解题脚本：

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import shutil
import subprocess
from pathlib import Path


HEADER = b"MINILCTF\x00\x00"
KEY_PREFIX = b"miniL-audio-key"
META_PREFIX = b"miniL:"
COMMENT_PREFIX = b"miniL meta:"
KEY_SEED_PREFIX = b"KaguyaIrohaYachiyo"


def main() -> None:
    args = parse_args()
    if shutil.which("openssl") is None:
        raise SystemExit("openssl not found in PATH")

    data = args.input.read_bytes()
    if not data.startswith(HEADER):
        raise SystemExit("bad container header")

    base_ts = args.timestamp or int(args.input.stat().st_mtime)
    ts, audio, meta, image = try_decrypt(data, base_ts, max(args.search, 0))

    out_dir = args.output_dir or args.input.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.stem or args.input.stem

    # 写入解密后的音频（题目中为 mp3 格式）
    if audio.startswith(b"fLaC"):
        audio_ext = "flac"
    elif audio.startswith(b"ID3") or audio[:2] == b"\xFF\xFB":
        audio_ext = "mp3"
    else:
        audio_ext = "bin"
    audio_path = out_dir / f"{stem}.{audio_ext}"
    audio_path.write_bytes(audio)
    print(f"[+] decrypted audio → {audio_path}")

    # 写入元数据
    meta_path = out_dir / f"{stem}.json"
    meta_path.write_bytes(meta)
    print(f"[+] metadata → {meta_path}")

    # 写入封面图片
    if image:
        ext = "png" if image.startswith(b"\x89PNG") else "jpg"
        img_path = out_dir / f"{stem}.{ext}"
        img_path.write_bytes(image)
        print(f"[+] cover image → {img_path}")

    print(f"[*] timestamp = {ts}")
    # ID3 标签中有提示 "Do you know FFT?"，指向频谱图
    print(f"[*] 用 Audacity/Sonic Visualiser 查看 {audio_path} 的频谱图即可看到 flag")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="wyy challenge solver")
    parser.add_argument("input", nargs="?", type=Path, default=Path("flag.enc"))
    parser.add_argument("--timestamp", type=int, help="手动指定时间戳")
    parser.add_argument("--search", type=int, default=10000, help="爆破半径（秒）")
    parser.add_argument("--output-dir", type=Path, help="输出目录")
    parser.add_argument("--stem", help="输出文件名前缀")
    return parser.parse_args()


def try_decrypt(data: bytes, base_ts: int, radius: int):
    candidates = [base_ts]
    for delta in range(1, radius + 1):
        candidates.append(base_ts + delta)
        candidates.append(base_ts - delta)

    for ts in candidates:
        core_key, meta_key = derive_keys(ts)
        try:
            audio, meta, image = decrypt(data, core_key, meta_key)
            return ts, audio, meta, image
        except Exception:
            continue
    raise SystemExit(f"failed to decrypt around ts={base_ts} +/-{radius}s")


def derive_keys(ts: int):
    digest = hashlib.sha256(KEY_SEED_PREFIX + str(ts).encode()).digest()
    return digest[:16], digest[16:]


def decrypt(data: bytes, core_key: bytes, meta_key: bytes):
    pos = len(HEADER)

    # 解密 key frame → audio_key
    key_frame, pos = read_frame(data, pos)
    key_frame = bytes(b ^ 0x64 for b in key_frame)
    plain = aes128_ecb_decrypt(key_frame, core_key)
    if not plain.startswith(KEY_PREFIX):
        raise ValueError("bad key frame")
    audio_key = plain[len(KEY_PREFIX):]

    # 解密 meta frame
    meta_frame, pos = read_frame(data, pos)
    meta_frame = bytes(b ^ 0x63 for b in meta_frame)
    if not meta_frame.startswith(COMMENT_PREFIX):
        raise ValueError("bad meta prefix")
    payload = base64.b64decode(meta_frame[len(COMMENT_PREFIX):])
    meta_plain = aes128_ecb_decrypt(payload, meta_key)
    if not meta_plain.startswith(META_PREFIX):
        raise ValueError("bad meta")
    meta = meta_plain[len(META_PREFIX):]

    # 跳过 5 字节零 + image_offset + image_data
    pos += 5
    image_offset = int.from_bytes(data[pos:pos + 4], "little")
    pos += 4
    image, pos = read_frame(data, pos)
    if image_offset > len(image):
        pos += image_offset - len(image)

    # 解密音频
    audio = xor_audio(data[pos:], audio_key)
    return audio, meta, image


def aes128_ecb_decrypt(data: bytes, key: bytes) -> bytes:
    proc = subprocess.run(
        ["openssl", "enc", "-aes-128-ecb", "-d", "-nopad", "-nosalt", "-K", key.hex()],
        input=data, check=True, capture_output=True,
    )
    result = proc.stdout
    # PKCS7 unpad
    pad = result[-1]
    if pad == 0 or pad > 16 or result[-pad:] != bytes([pad]) * pad:
        raise ValueError("bad pkcs7")
    return result[:-pad]


def xor_audio(data: bytes, key: bytes) -> bytes:
    box = list(range(256))
    j = 0
    for i in range(256):
        j = (box[i] + j + key[i % len(key)]) & 0xFF
        box[i], box[j] = box[j], box[i]

    plain = bytearray(data)
    for i in range(len(plain)):
        j = (i + 1) & 0xFF
        plain[i] ^= box[(box[j] + box[(box[j] + j) & 0xFF]) & 0xFF]
    return bytes(plain)


def read_frame(data: bytes, pos: int):
    size = int.from_bytes(data[pos:pos + 4], "little")
    return data[pos + 4:pos + 4 + size], pos + 4 + size


if __name__ == "__main__":
    main()
```

### Step 3: 查看频谱图

解密得到的 mp3 文件用 Audacity 打开，切换到频谱图（Spectrogram）视图，在音频末尾段可见 flag 文本。

也可以用 Python 直接渲染（需要先将 mp3 转为 wav）：

```python
import subprocess
from pathlib import Path
import numpy as np
from scipy.io import wavfile
from scipy.signal import stft
from PIL import Image

def mp3_to_wav(mp3_path: Path) -> Path:
    wav_path = mp3_path.with_suffix(".wav")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(mp3_path), "-ar", "48000", "-ac", "2", str(wav_path)],
        check=True,
    )
    return wav_path

wav = mp3_to_wav(Path("flag.mp3"))
sr, audio = wavfile.read(str(wav))
signal = audio[:, 0].astype(np.float32)
_, _, Z = stft(signal, fs=sr, window="hann", nperseg=4096, noverlap=3840)
spec = np.abs(Z[:, -8000:])  # flag 在末尾前约 38s~18s 的位置
spec_db = 20 * np.log10(np.clip(spec, 1e-10, None))
img = np.clip((spec_db + 80) / 80 * 255, 0, 255).astype(np.uint8)
Image.fromarray(np.flipud(img)).save("spectrogram.png")
```

## Flag

```
miniL{Yur1_1s_JusT1c3!!F0ll0w_Ch0u-K@guy@-h1me!th@nks_m03w}
```
