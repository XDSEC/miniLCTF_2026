# wyy

`wyy` 是 miniLCTF_2026 逆向题目的出题侧打包工具。它把普通音频、英文 metadata 和可选封面图封装成类 NCM 的加密音频文件。

## 用法

```bash
cargo run --release -- pack <audio> <meta.json> <output.wyy> [cover-image]
```

示例：

```bash
cargo run --release -- pack flag_spectrum.mp3 examples/meta.json dist/kaguya.wyy cover.png
```

## 题目设计

- 文件格式复刻 ncmc 支持的 NCM 容器结构和音频流异或算法。
- key frame 使用一把 AES core key，metadata frame 使用另一把 AES meta key，音频本体使用 key frame 解出的 RC4-like keystream。
- 二进制里存在两段明文 fake key：`YachiyoNanami!!!` 和 `YachiyoMitsuru!!`。
- 程序加载时通过 ELF `.init_array` 对 fake key 做分散字节补丁，运行时变成 Kaguya 相关的 core/meta key。
- metadata 只放英文内容，建议用于提示 Kaguya、Iroha、Yachiyo 和 spectrum。
- 真正 flag 由出题人藏在解密后音频的频谱中，本工具不会修改输入音频内容。

## 给选手的建议文件

- 编译后的 `wyy` 二进制。
- 由本工具生成的 `.wyy` 加密音频。
- 中文题面，不要直接给本 README。

## 本地验证

```bash
cargo test
```

测试会检查：

- `.init_array` 是否把 Yachiyo fake keys 替换成 Kaguya real keys。
- 打包后的文件是否能用 real key 解回原始音频、metadata 和封面。
- fake key 是否无法打开生成的文件。
