# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个 miniLCTF_2026 的逆向工程题目，主题基于电影《超时空辉夜姬》。题目将 flag 以频谱图水印的形式隐藏在音频文件中，然后加密为自定义 `.enc` 容器。选手需要根据文件修改时间爆破出加密密钥。

## 构建与测试命令

```bash
# 构建 wyy Rust 加密工具（release）
cargo build --release --manifest-path wyy/Cargo.toml

# 运行 Rust 测试
cargo test --manifest-path wyy/Cargo.toml

# 完整出题构建流程（需要 ffmpeg、openssl）
scripts/build_dist.sh --input song.mp3 --output flag.mp3 --flag-text 'miniL{...}'

# 仅生成频谱图水印音频
uv run scripts/spectrogram_flag.py song.mp3 flag.mp3 'miniL{...}' --preview preview.png

# 解密 wyy 容器（参考解题脚本）
uv run scripts/decrypt_audio.py dist/flag.enc --output-dir /tmp/out
```

## 架构

### 出题流程

1. **`scripts/spectrogram_flag.py`** — 将文本渲染为图像，利用 STFT 将图像作为二值掩码"烙印"到音频频谱中（将掩码区域的频点幅度清零）。水印插入在音频末尾段（默认最后 20 秒，往前留 18 秒缓冲）。
2. **`wyy/`（Rust crate）** — 将带水印的音频打包为 `.enc` 容器：元数据用 AES-128-ECB 加密，音频数据用 RC4 变体 XOR 加密。
3. **`scripts/build_dist.sh`** — 编排完整出题流程：生成水印音频 → 写入 ID3 提示标签 → 编译 `wyy` → 打包输出到 `dist/`。

### 密钥派生（题目核心）

- `derive_keys(ts)` = SHA256(`"KaguyaIrohaYachiyo"` + `ts.to_string()`)，其中 `ts` 是 Unix 时间戳（秒）。
- 前 16 字节 → `core_key`（加密音频密钥帧）。
- 后 16 字节 → `meta_key`（加密元数据帧）。
- `build.rs` 在编译时将合法时间戳范围约束为 `(编译时间秒数 / 10000) ± 20000` 个桶，运行时通过 `assert!` 强制校验。这限制了选手的爆破搜索空间。

### wyy 容器格式

```
HEADER (10 字节: "MINILCTF\0\0")
→ key_frame:  [u32 LE 长度] [AES-ECB 加密的 KEY_PREFIX + audio_key, 然后逐字节 xor 0x64]
→ meta_frame: [u32 LE 长度] [AES-ECB 加密的 META_PREFIX + json, base64 编码并带 COMMENT_PREFIX 前缀, 然后逐字节 xor 0x63]
→ 5 字节零
→ image_offset: u32 LE
→ 图片数据
→ 音频数据 (NcmRc4 流密码 XOR 加密)
```

### NcmRc4 音频加密

魔改 RC4 变体。Key box 生成为标准 KSA，但 PRGA 使用非标准索引计算：`state[(state[j] + state[(state[j] + j) & 0xFF]) & 0xFF]`。音频密钥为 64 字节，由 core_key 的 16 字节经过 4 轮旋转和混合生成。

### Python 脚本（Python ≥3.12, uv 管理依赖）

- **`scripts/decrypt_audio.py`** — 参考解题脚本。通过调用 `openssl` CLI 做 AES-128-ECB 解密（不依赖 pycryptodome）。以文件 mtime 为中心，按扩展增量顺序（0, +1, -1, +2, -2, ...）爆破时间戳。
- **`scripts/spectrogram_flag.py`** — 重度依赖（`numpy`, `scipy`, `pillow`, `mutagen`）。通过 `ffmpeg` 做音频读写和编码。flag 文本用 Pillow 渲染后垂直翻转，作为二值掩码作用到 STFT 幅度上，再通过逆 STFT 重建音频。
- **`verify_challenge_symbols/recover_wyy.py`** — 独立工具，用于恢复原始 `.wyy`（网易云格式）文件，不是题目流程的一部分。使用不同的密钥派生方式（硬编码的 `KEY_ORDER`/`KEY_PATCH` 表）。

### ncmc/

上游 `ncmc` 项目（网易云音乐转换器）。题目构建不直接使用，作为加密算法和容器格式的参考来源。`wyy` crate 复用了相同的加密逻辑，仅替换了常量。
