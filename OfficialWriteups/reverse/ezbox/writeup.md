# ezbox — Official Writeup

## Challenge

一个终端推箱子游戏，10 层汉诺塔 + 递归方块。完成所有关卡获得 flag。

附件：`ezbox`（Linux ELF，PyInstaller 打包）

---

## 解法一：玩游戏通关

解包反编译后，直接在 Python 里导入游戏模块，模拟按键操作完成全部 1024 个上下文。

### 1. 解包 & 反编译

```bash
# 1. 解包
pyinstxtractor ezbox

# 2. 上传 .pyc 到 https://www.pylingual.io/ 反编译
# 得到 main.py, game.py, levels.py, flag.py 源码
```

解包后目录里包含所有 `.pyc` 和 `_core.so`，**Python 可以直接 import `.pyc`**，无需修复反编译代码。用 pylingual 只是为了读懂游戏逻辑。注意 Python 版本要与打包环境一致（3.12）。

### 2. 理解游戏机制

- 关卡 `h0`（基案）：一个箱子 `b`，推上 `_` 目标，玩家站到 `=` 就算完成
- 关卡 `h1`~`h10`：汉诺塔布局，方块 `0`~`N-1` 堆在柱 A（x=2），目标在柱 C（x=15）
- 走进入未完成的递归方块 → 进入子关卡。子关卡完成后方块解锁，可推动。
- 每次进入子关卡产生唯一上下文路径（`h10` → `h10/0` → `h10/1/0` → ...）
- `completed_hashes` 追踪所有已完成的上下文

### 3. 编写游戏 AI

核心思路：对于每个关卡，按顺序（从上到下）处理方块：
1. 走到方块左侧（x=1 列，没有实体挡路）
2. 往右推 → 进入（未完成时）或推动（已完成时）
3. 进入后递归处理子关卡
4. 退出后把方块推到目标（x=15）
5. 最终走向 `=` 完成关卡

```python
from game import Game
from flag import try_get_flag
from levels import load_level_file, RECURSIVE_BLOCKS

def walk_to(game, tx, ty):
    """走到 (tx, ty)，通过 x=1 空列规避实体"""
    px, py = game.player_pos
    while px > 1: game.move(-1, 0); px = game.player_pos[0]
    while px < 1: game.move(1, 0); px = game.player_pos[0]
    while py < ty: game.move(0, 1); py = game.player_pos[1]
    while py > ty: game.move(0, -1); py = game.player_pos[1]
    while px < tx: game.move(1, 0); px = game.player_pos[0]

def solve_level(level_id, game, context):
    terrain, entities, player_pos = load_level_file(level_id)
    game.load_level(level_id, terrain, entities, player_pos,
                    level_id, context=context)

    if level_id == 'h0':
        game.move(1,0); game.move(0,1); game.move(1,0)
        game.move(0,1); game.move(0,1)
        if game.check_completion(): game.complete_level()
        return

    blocks = sorted([(p, e) for p, e in entities.items() if e != 'p'],
                    key=lambda x: (x[0][1], x[0][0]))

    for (bx, by), bid in blocks:
        if bid in RECURSIVE_BLOCKS and not game.is_block_completed(bid):
            walk_to(game, 1, by)
            result = game.move(1, 0)
            if result and result.startswith('enter:'):
                game.enter_block(bid)
                solve_level(f'h{bid}', game, f'{context}/{bid}')
                game.exit_block()

        cur = next((p for p, e in game.entities.items() if e == bid), None)
        if not cur: continue
        cx, cy = cur
        walk_to(game, cx - 1, cy)
        for _ in range(15 - cx): game.move(1, 0)

    eq = next((p for p, c in terrain.items() if c == '='), None)
    if eq:
        walk_to(game, 1, eq[1])
        while game.player_pos[0] < eq[0] - 1: game.move(1, 0)
        game.move(1, 0)
    if game.check_completion(): game.complete_level()


game = Game()
solve_level('h10', game, 'h10')
print(try_get_flag(game.completed_hashes, game.total_steps))
```

`cd` 进解包目录后运行。完整脚本见附件 `solve.py`。

---

## 解法二：逆向 Python 代码直接算密钥

不需要实际玩游戏。1024 个上下文哈希只依赖**固定地形上的目标位置**，可以直接从关卡文件计算。

### 1. 理解密钥派生

反编译 `flag.py` 后看到：

```python
def derive_key(completed_hashes):
    combined = ''.join(completed_hashes[lp] for lp in sorted(completed_hashes))
    return hashlib.sha256(combined.encode()).digest()[:16]

def hash_level_state(level_path, goals_str):
    data = f"{level_path}|{goals_str}"
    return hashlib.sha256(data.encode()).hexdigest()
```

密钥 = 把所有 1024 个上下文哈希按字典序串联 → SHA256 → 前 16 字节。

每个上下文哈希 = `SHA256("h10/1/0|2,3;3,4")` 这种形式，只依赖该上下文对应关卡的 `_` 和 `=` 位置。

### 2. 生成 1024 个上下文并计算哈希

`levels.py` 里的 `collect_all_context_paths()` 可以列出全部 1024 个上下文。每个上下文的关卡文件取其最后一段（`h10/1/0` → `h0`）。

```python
from levels import load_level_file, collect_all_context_paths
from flag import hash_level_state, derive_key

def file_for_context(ctx):
    """h10/1/0 → h0, h10 → h10"""
    last = ctx.rsplit('/', 1)[-1]
    return last if last.startswith('h') else f'h{last}'

contexts = collect_all_context_paths()
hashes = {}
for ctx in sorted(contexts):
    file_id = file_for_context(ctx)
    terrain, _, _ = load_level_file(file_id)
    goals = sorted(f'{x},{y}' for (x,y), c in terrain.items() if c in '=_')
    hashes[ctx] = hash_level_state(ctx, ';'.join(goals))

key = derive_key(hashes)
```

### 3. 解密 flag

flag 加密字节在 `_core.so` 里。可以用 IDA 提取，也可以直接用 Python 的 `_core.decrypt(key)` 调用（反正已经 import 进来了）：

```python
from _core import decrypt
print(decrypt(key))
# miniL{EZ_Hano1_ez_s1gn1n_r1ght?}
```

`cd` 进解包目录后运行。

---

## 知识点总结

| 考点 | 说明 |
|------|------|
| PyInstaller 解包 | pyinstxtractor 提取 .pyc |
| Python 反编译 | pylingual.io 在线反编译，pycdc 备选 |
| 原生逆向 | IDA 分析 `_core.so`（XXTEA + 嵌入加密字节） |
| 汉诺塔结构 | 方块 K → 子关卡 hK，递归上下文 h10/1/0... |
| 哈希链分析 | 1024 个上下文哈希只依赖固定地形 |
| 绕过游戏 | 不玩游戏直接算哈希链 |

## Flag

```
miniL{EZ_Hano1_ez_s1gn1n_r1ght?}
```
