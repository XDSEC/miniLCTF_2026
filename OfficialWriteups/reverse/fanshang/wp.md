**Schrodinger's Env **

- **核心目标**: 同时满足两个环境标签（`hooked:maps` 和 `hooked:token`）并输入正确接入码，KDF 才派生正确 key 解出真 flag；否则只返回诱饵 `fakeflag`。
- **接入码恢复**: 输入规范化（只保留字母数字、全小写）后做 FNV-1a64 校验；题目标题规范化后即为正确接入码（schrodingersenv）。
- **环境检测点**: 读取 `/proc/self/maps`（查找 XposedBridge.jar → `hooked:maps` / 否则 `clean:maps`）与系统属性 `ro.security.magic_token`（与从 `assets/compat_profile.dat` 解出的期望 token 比较 → `hooked:token`）。
- **token 恢复**: 从 APK 资源 `assets/compat_profile.dat` 解码（头 `CFG1`、长度、seed、异或还原）可得 `masochistic.sdk::grant_key_v1`，无需外部信息。
- **判定与解密**: maps_feature 与 token_feature 经哈希/KDF 派生 16 字节 key，用于解密内置密文并检查前缀 `MSDK|`；命中则为真 flag，否则走诱饵分支。
- **可行解法**: 静态还原接入码与 token，然后动态伪造检测结果（Hook `__system_property_get`、拦截/伪造 `/proc/self/maps` 读取或 patch native），或完整复现 KDF 离线解密获得 flag。

**snake_minil**

- **概况**: 64 位 PE 贪吃蛇，隐藏 0x480 字节 blob。游戏按键会触发对该 blob 的一系列变换；吃到食物后计算 blob 的 MD5，命中目标 MD5 会触发 finalizer，用派生 key 逆运算还原最终 flag（有调试时的假成功链）。
- **隐藏变换与按键映射**: 变换字母表 `P A L S`，含义：
  - `A`: 每字节 +0x1e
  - `S`: 每字节 -0x66
  - `L`: byte 左循环移位 3
  - `P`: 整体循环左移 6 字节
  按键映射：`U->P, D->A, L->L, R->S`。按键按 `lastChangedKey` 去重，首个有效按键必触发变换。
- **路线与操作序列**: 前 10 个食物位置固定，采用水平优先最短路得到总 tick 序列并压缩为触发变换的按键序列 `RULDLDRULDLURDLURD`，对应操作序列 `SPLALASPLALPSALPSA`，最终 MD5 为 `cac0dfcf4b795ee7436b17721d2411e1`。
- **派生 key 与解密**: 命中 MD5 后从当前 blob 派生 TEA key（给出混合/rol32 算法），用该 key 对 16 字节密文做逆 TEA 得到明文 `miniL{r0ut3_Snk}`。调试态另有 decoy MD5 导致假 flag。
- **可行解法**: 重放官方最短路线或直接脚本化对 blob 应用操作序列计算 MD5，命中后用等价派生逻辑生成 key 并逆运算密文得到 flag；避免在调试器下运行以免触发假链。