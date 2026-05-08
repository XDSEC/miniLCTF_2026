# Vectorized Mirage: Revenge Writeup

## 题目概述

> 注：本题题解参考2024强网杯 https://blog.hxzzz.asia/archives/311/  ez_vm

这题的核心是一个被虚拟化保护包裹的 VM checker。选手拿到的只有发布版二进制，`VIRTUALIZER_START` 到 `VIRTUALIZER_END` 之间的内容一律视为不可见黑盒（CodeVirtualizer商业化虚拟机）。题目预期解也建立在这个假设上：

1. 不去尝试读出 VM dispatcher 的虚拟化实现。
2. 利用未虚拟化的 handler 边界进行 hook 和运行时观测。
3. 从运行时调用参数和内存中的白盒表恢复出等价的白盒 AES-256 网络。
4. 通过 DFA 恢复轮密钥，最终回推出明文 flag。

最终 flag：

```text
miniL{Y0u_R_VM_Mast3r!}
```

## 一、黑盒视角下先做什么

发布版程序行为非常简单：

```text
flag> ...
accepted / rejected
```

输入长度要求是 16 字节，或者 `miniL{...}` 格式中花括号里的 16 字节。

在黑盒前提下，第一步目标只有两个：

1. 证明程序内部对 16 字节块做了确定性的分组变换。
2. 找出哪些位置依然可观察、可插桩。

### 1.1 动态观察可见边界

虽然 dispatcher 在虚拟化壳里，handler 本身依然是普通函数，原因是题目构建时显式关闭了内联，并给每个 handler 都加了 `noinline`。因此在发布版里可以稳定看到一组很短的小函数，特征非常鲜明：

1. 一类函数只做栈操作。
2. 一类函数只做 `state[16]` / `scratch[32]` 读写。
3. 三个函数会访问巨大的只读查表区。

这三个查表函数就是后面的关键：

1. `h_wb_init`
2. `h_wb_mid`
3. `h_wb_final`

题目真正的密码学逻辑全部落在这三类 handler 上，其他 VM 指令都是胶水。

### 1.2 为什么 hook handler 足够

因为 dispatcher 虽然不可见，但它每次仍然要把 opcode 路由到对应 handler。只要能在 handler 入口或出口记录以下信息，就已经够还原完整语义：

1. 当前 handler 类型。
2. handler 的立即数参数。
3. handler 从 VM 栈顶弹出的字节值。
4. handler 压回栈顶的结果值。
5. `state` / `scratch` 的索引。

换句话说，这道题不需要看见 dispatcher 怎么写，只需要把它当成“不断调用这些小函数的黑盒调度器”。

## 二、先把 VM 层剥掉

### 2.1 handler 语义

通过动调和少量反汇编，可以很快确认几类基础指令：

1. `LOAD_STATE i` / `STORE_STATE i`
2. `LOAD_SCR i` / `STORE_SCR i`
3. `XOR`
4. `HALT`
5. 一些明显没有业务价值的噪声指令

其中真正影响密码逻辑的控制流很规整：

1. 先对 16 个 `state` 字节各做一次 `WB_INIT`
2. 接着重复 13 轮 `WB_MID`
3. 最后做一轮 `WB_FINAL`
4. 结果再进入最终比较

即使完全不看虚拟化区域，只靠 handler 调用序列也能恢复这条主流程。

### 2.2 VM 程序结构

把一次成功运行中的 handler 序列记录下来后，很容易发现每轮结构高度重复：

1. 对每一列的 4 个输出字节分别累积 4 项贡献。
2. 每个输出字节都是 4 次 `WB_MID` 结果异或起来。
3. 暂存到 `scratch`。
4. 再整体搬回 `state`。

这是非常典型的白盒 AES 列混合形态：

```text
单字节查表 -> 四项异或合并 -> 形成新一列
```

到这里已经可以合理怀疑这是白盒 AES，而不是自定义分组算法。

## 三、最终比较先逆掉

在黑盒题里，优先把最终比较逆出来，因为这一步最稳定，也能立刻给出目标密文。

最终比较不是直接和常量逐字节比较，而是做了一个置换加掩码：

```c
index = (i * 5 + 3) & 15
mask  = rotl8(0x71 + 0x33 * i, i & 7)
diff |= (output[index] ^ mask) ^ blob[i]
```

把它逆回去就得到白盒 AES 的目标输出块：

```text
37 9c 79 a0 c4 f1 55 69 75 b5 41 8f ce ab 88 fa
```

也就是：

```text
379c79a0c4f1556975b5418fceab88fa
```

后面所有工作都变成：

```text
求一个 16 字节明文 P，使得 白盒AES(P) = 379c79a0c4f1556975b5418fceab88fa
```

## 四、识别白盒表的真实形态

题目里最重要的证据是三块大查表：

1. `kInit[16][256]`
2. `kMid[13][4][4][4][256]`
3. `kFinal[16][256]`

它们的维度本身已经很说明问题：

1. `16` 个字节位
2. `13` 个中间轮
3. `4x4` 的列和行关系
4. 每个表项输入都是一个字节

这正好对应 AES-256：

1. 初始轮一次
2. 中间轮 13 次
3. 末轮一次

总共 14 轮。

### 4.1 `kInit` 的含义

对每个位置 `i`，`kInit[i]` 都是一个 256 项字节置换表，形态可以直接拟合成：

```text
kInit[i][x] = x ^ a0[i]
```

也就是初始 AddRoundKey。

从表中直接取 `kInit[i][0]` 就能拿到第 0 轮轮密钥字节：

```text
05 93 0f 0d af dd dd 5a dc 15 3f c0 4e 22 57 1d
```

这一步非常重要，因为它说明白盒没有做更深的输入编码，初始层只是单纯异或轮密钥。

### 4.2 `kFinal` 的含义

对每个 `kFinal[out_idx]`，都能唯一拟合为：

```text
kFinal[out_idx][x] = Sbox[x ^ a[out_idx]] ^ b[out_idx]
```

这就是末轮标准结构：

```text
AddRoundKey -> SubBytes -> output encoding
```

注意这里有一个输出字节编码 `b[out_idx]`，它解释了为什么直接把表当成标准 AES 的末轮时会看到额外偏移。

### 4.3 `kMid` 的含义

中间轮表最关键。把每个 `kMid[round][column][source_row][output_row]` 拿出来拟合，都会唯一落到下面的形式：

```text
kMid[r][c][sr][or][x] = MC[or][sr] * Sbox[x ^ a_r[src]] ^ b_r[c,or,sr]
```

其中：

1. `MC` 是 AES 的 MixColumns 系数矩阵
2. `a_r[src]` 是该源字节对应的轮密钥掩码
3. `b_r[...]` 是白盒输出编码带来的常量项

AES 的 MixColumns 系数矩阵正好对应观测结果：

```text
2 3 1 1
1 2 3 1
1 1 2 3
3 1 1 2
```

每个输出字节会把 4 个这样的单字节贡献异或起来，所以同一列的 4 个 `b_r[...]` 也会一起异或成一个列常量。

到这里，白盒表的真实结构已经完全落地：

```text
中间轮 = ShiftRows 后的单字节 Sbox 查表 + MixColumns 线性组合 + 输出编码常量
```

这就是标准白盒 AES。

## 五、预期解是 hook + DFA

1. hook `h_wb_init` / `h_wb_mid` / `h_wb_final`
2. 在运行时把每张表的输入输出关系导出来
3. 把白盒表拟合成标准 AES 的单字节贡献
4. 再对白盒做 DFA

这条路线有两个优点：

1. 完全不依赖看见虚拟化 dispatcher
2. 即使白盒表不在静态段，运行时也能导出

### 5.1 推荐 hook 点

最省事的是直接 hook 这三个 handler：

1. `h_wb_init(vm)`
2. `h_wb_mid(vm)`
3. `h_wb_final(vm)`

记录字段建议如下：

```text
handler 类型
立即数参数
输入字节 value
输出字节 result
轮号 / 列号 / source_row / output_row
```

当你给 256 个不同输入跑足够多次，或者直接在 handler 内部遍历 0..255 测试输入，就能把整张白盒表导出来。

### 5.2 题目里的 DFA 入口

题目预期思路里，选手在拿到等价白盒表以后，下一步是做故障注入。最自然的 fault 点有两个：

1. 某一轮 `WB_MID` 的输出写回 `scratch` 之前
2. 最后一轮前的 `state` 某个字节

对 AES 而言，倒数第二轮列上的单字节故障会在末轮输出形成 4 字节差分。这正是经典 DFA 场景：

```text
2e,1e,1e,3e
1e,2e,3e,1e
1e,3e,2e,1e
3e,1e,1e,2e
```

这里的 `e` 是某个 GF(2^8) 上的故障值。

因为我们已经通过 hook 把末轮的输出编码 `b[out_idx]` 拟合掉了，所以 DFA 直接可以在“解码后的标准 AES 末轮输出”上进行。这样恢复的是末轮轮密钥 `K14`。

## 六、从白盒恢复等价 AES-256

虽然题目预期是 DFA，这里把完整恢复过程也写出来，方便赛后复现。

### 6.1 先解码目标输出

最终比较逆出来的目标块是：

```text
C = 379c79a0c4f1556975b5418fceab88fa
```

### 6.2 逆掉 `kFinal`

对每个输出字节：

```text
state_before_final[src] = InvSbox(C[out] ^ b[out]) ^ a_final[src]
```

这里 `src` 和 `out` 的对应关系来自末轮的 ShiftRows 布局：

```text
src = ((column + row) & 3) * 4 + row
out = column * 4 + row
```

### 6.3 逆 13 个中间轮

对每个中间轮，按下面三步逆回去：

1. 先把每个输出字节异或掉聚合常量 `d_r[out]`
2. 对每一列做 `InvMixColumns`
3. 对每个源字节做 `InvSbox` 并异或掉该轮字节掩码 `a_r[src]`

公式写成：

```text
W[out] = state[out] ^ d_r[out]
Z[col] = InvMixColumns(W[col])
prev[src] = InvSbox(Z[src]) ^ a_r[src]
```

### 6.4 最后逆掉 `kInit`

```text
plain[i] = state[i] ^ a0[i]
```

逆完以后得到的 16 字节明文是：

```text
59 30 75 5f 52 5f 56 4d 5f 4d 61 73 74 33 72 21
```

ASCII 即：

```text
Y0u_R_VM_Mast3r!
```

因此 flag 是：

```text
miniL{Y0u_R_VM_Mast3r!}
```

## 七、验证

对发布版程序做验收：

```text
miniL{Y0u_R_VM_Mast3r!} -> accepted
Y0u_R_VM_Mast3r!       -> accepted
miniL{AAAAAAAAAAAAAAAA} -> rejected
```

说明恢复结果正确。

## 十、题目源码

```cpp
#include <array>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>

#if defined(__has_include)
#if __has_include(<VirtualizerSDK.h>)
#include <VirtualizerSDK.h>
#endif
#include <intrin.h>
#endif
#include <algorithm>

#include "WbTables.inc"

#ifndef VIRTUALIZER_START
#define VIRTUALIZER_START
#endif

#ifndef VIRTUALIZER_END
#define VIRTUALIZER_END
#endif

#if defined(_MSC_VER)
#define VM_NOINLINE __declspec(noinline)
#else
#define VM_NOINLINE __attribute__((noinline))
#endif

namespace
{
using u8 = std::uint8_t;
using usize = std::size_t;

struct Vm
{
    const std::vector<u8>* code = nullptr;
    std::array<u8, 16> state{};
    std::array<u8, 32> scratch{};
    std::array<u8, 512> stack{};
    usize pc = 0;
    usize sp = 0;
    u8 noise = 0;
    bool running = true;
    bool fault = false;
};

enum Op : u8
{
    OP_HALT = 0,
    OP_PUSH_IMM,
    OP_LOAD_STATE,
    OP_STORE_STATE,
    OP_XOR,
    OP_DUP,
    OP_DROP,
    OP_SWAP,
    OP_ADD,
    OP_SUB,
    OP_ROL,
    OP_ROR,
    OP_AND,
    OP_OR,
    OP_NOT,
    OP_LOAD_SCR,
    OP_STORE_SCR,
    OP_EQ,
    OP_BOGUS,
    OP_WB_INIT,
    OP_WB_MID,
    OP_WB_FINAL,
    OP_COUNT
};

static const u8 kExpectedBlob[16] = {
    0xd1, 0x3c, 0xf4, 0x29, 0xba, 0xc0, 0x74, 0x3e,
    0x86, 0x4f, 0x4c, 0x54, 0xa7, 0xc5, 0x7b, 0xbf
};

VM_NOINLINE u8 rotl8(u8 value, unsigned amount)
{
    amount &= 7;
    if (amount == 0)
    {
        return value;
    }
    return static_cast<u8>((value << amount) | (value >> (8 - amount)));
}

VM_NOINLINE u8 rotr8(u8 value, unsigned amount)
{
    amount &= 7;
    if (amount == 0)
    {
        return value;
    }
    return static_cast<u8>((value >> amount) | (value << (8 - amount)));
}

VM_NOINLINE void wipe_bytes(u8* data, usize size)
{
    volatile u8* p = data;
    while (size-- != 0)
    {
        *p++ = 0;
    }
}

VM_NOINLINE u8 fetch(Vm& vm)
{
    if (vm.pc >= vm.code->size())
    {
        vm.fault = true;
        vm.running = false;
        return 0;
    }
    return (*vm.code)[vm.pc++];
}

VM_NOINLINE void push(Vm& vm, u8 value)
{
    if (vm.sp >= vm.stack.size())
    {
        vm.fault = true;
        vm.running = false;
        return;
    }
    vm.stack[vm.sp++] = value;
}

VM_NOINLINE u8 pop(Vm& vm)
{
    if (vm.sp == 0)
    {
        vm.fault = true;
        vm.running = false;
        return 0;
    }
    return vm.stack[--vm.sp];
}

VM_NOINLINE void h_halt(Vm& vm)
{
    vm.running = false;
}

VM_NOINLINE void h_push_imm(Vm& vm)
{
    push(vm, fetch(vm));
}

VM_NOINLINE void h_load_state(Vm& vm)
{
    const u8 index = static_cast<u8>(fetch(vm) & 15u);
    push(vm, vm.state[index]);
}

VM_NOINLINE void h_store_state(Vm& vm)
{
    const u8 index = static_cast<u8>(fetch(vm) & 15u);
    vm.state[index] = pop(vm);
}

VM_NOINLINE void h_xor(Vm& vm)
{
    const u8 rhs = pop(vm);
    const u8 lhs = pop(vm);
    push(vm, static_cast<u8>(lhs ^ rhs));
}

VM_NOINLINE void h_dup(Vm& vm)
{
    const u8 value = pop(vm);
    push(vm, value);
    push(vm, value);
}

VM_NOINLINE void h_drop(Vm& vm)
{
    (void)pop(vm);
}

VM_NOINLINE void h_swap(Vm& vm)
{
    const u8 rhs = pop(vm);
    const u8 lhs = pop(vm);
    push(vm, rhs);
    push(vm, lhs);
}

VM_NOINLINE void h_add(Vm& vm)
{
    const u8 rhs = pop(vm);
    const u8 lhs = pop(vm);
    push(vm, static_cast<u8>(lhs + rhs));
}

VM_NOINLINE void h_sub(Vm& vm)
{
    const u8 rhs = pop(vm);
    const u8 lhs = pop(vm);
    push(vm, static_cast<u8>(lhs - rhs));
}

VM_NOINLINE void h_rol(Vm& vm)
{
    const u8 amount = fetch(vm);
    push(vm, rotl8(pop(vm), amount));
}

VM_NOINLINE void h_ror(Vm& vm)
{
    const u8 amount = fetch(vm);
    push(vm, rotr8(pop(vm), amount));
}

VM_NOINLINE void h_and(Vm& vm)
{
    const u8 rhs = pop(vm);
    const u8 lhs = pop(vm);
    push(vm, static_cast<u8>(lhs & rhs));
}

VM_NOINLINE void h_or(Vm& vm)
{
    const u8 rhs = pop(vm);
    const u8 lhs = pop(vm);
    push(vm, static_cast<u8>(lhs | rhs));
}

VM_NOINLINE void h_not(Vm& vm)
{
    push(vm, static_cast<u8>(~pop(vm)));
}

VM_NOINLINE void h_load_scr(Vm& vm)
{
    const u8 index = static_cast<u8>(fetch(vm) & 31u);
    push(vm, vm.scratch[index]);
}

VM_NOINLINE void h_store_scr(Vm& vm)
{
    const u8 index = static_cast<u8>(fetch(vm) & 31u);
    vm.scratch[index] = pop(vm);
}

VM_NOINLINE void h_eq(Vm& vm)
{
    const u8 rhs = pop(vm);
    const u8 lhs = pop(vm);
    push(vm, static_cast<u8>(lhs == rhs ? 1 : 0));
}

VM_NOINLINE void h_bogus(Vm& vm)
{
    const u8 value = fetch(vm);
    vm.noise = static_cast<u8>(rotl8(static_cast<u8>(vm.noise + value), value & 7u) ^ 0xa5u);
}

VM_NOINLINE void h_wb_init(Vm& vm)
{
    const u8 index = static_cast<u8>(fetch(vm) & 15u);
    const u8 value = pop(vm);
    push(vm, wb_tables::kInit[index][value]);
}

VM_NOINLINE void h_wb_mid(Vm& vm)
{
    const u8 round = static_cast<u8>(fetch(vm) % 13u);
    const u8 column = static_cast<u8>(fetch(vm) & 3u);
    const u8 source_row = static_cast<u8>(fetch(vm) & 3u);
    const u8 output_row = static_cast<u8>(fetch(vm) & 3u);
    const u8 value = pop(vm);
    push(vm, wb_tables::kMid[round][column][source_row][output_row][value]);
}

VM_NOINLINE void h_wb_final(Vm& vm)
{
    const u8 index = static_cast<u8>(fetch(vm) & 15u);
    const u8 value = pop(vm);
    push(vm, wb_tables::kFinal[index][value]);
}

#include <Windows.h>
VM_NOINLINE void dispatch(Vm& vm, u8 op)
{
    VIRTUALIZER_START;
    LARGE_INTEGER start, end, freq;
    QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&start);
    VIRTUALIZER_END;
    switch (op)
    {
    case OP_HALT:
    {
        VIRTUALIZER_START
            h_halt(vm);
        VIRTUALIZER_END
    }
        break;
    case OP_PUSH_IMM:
    {
        VIRTUALIZER_START
            h_push_imm(vm);
        VIRTUALIZER_END
    }
        break;
    case OP_LOAD_STATE:
    {
        VIRTUALIZER_START
            h_load_state(vm);
        VIRTUALIZER_END
    }
        break;
    case OP_STORE_STATE:
    {
        VIRTUALIZER_START
            h_store_state(vm);
        VIRTUALIZER_END
    }
        break;
    case OP_XOR:
    {
        VIRTUALIZER_START
            h_xor(vm);
        VIRTUALIZER_END
    }
        break;
    case OP_DUP:
    {
        VIRTUALIZER_START
            h_dup(vm);
        VIRTUALIZER_END
    }
        break;
    case OP_DROP:
    {
        VIRTUALIZER_START
            h_drop(vm);
        VIRTUALIZER_END
    }
        break;
    case OP_SWAP:
    {
        VIRTUALIZER_START
            h_swap(vm);
        VIRTUALIZER_END
    }
        break;
    case OP_ADD:
    {
        VIRTUALIZER_START
            h_add(vm);
        VIRTUALIZER_END
    }
        break;
    case OP_SUB:
    {
        VIRTUALIZER_START
            h_sub(vm);
        VIRTUALIZER_END
    }
        break;
    case OP_ROL:
    {
        VIRTUALIZER_START
            h_rol(vm);
        VIRTUALIZER_END
    }
        break;
    case OP_ROR:
    {
        VIRTUALIZER_START
            h_ror(vm);
        VIRTUALIZER_END
    }
        break;
    case OP_AND:
    {
        VIRTUALIZER_START
            h_and(vm);
        VIRTUALIZER_END
    }
        break;
    case OP_OR:
    {
        VIRTUALIZER_START
            h_or(vm);
        VIRTUALIZER_END
    }
        break;
    case OP_NOT:
    {
        VIRTUALIZER_START
            h_not(vm);
        VIRTUALIZER_END
    }
        break;
    case OP_LOAD_SCR:
    {
        VIRTUALIZER_START
            h_load_scr(vm);
        VIRTUALIZER_END
    }
        break;
    case OP_STORE_SCR:
    {
        VIRTUALIZER_START
            h_store_scr(vm);
        VIRTUALIZER_END
    }
        break;
    case OP_EQ:
    {
        VIRTUALIZER_START
            h_eq(vm);
        VIRTUALIZER_END
    }
        break;
    case OP_BOGUS:
    {
        VIRTUALIZER_START
            h_bogus(vm);
        VIRTUALIZER_END
    }
        break;
    case OP_WB_INIT:
    {
        VIRTUALIZER_START
            h_wb_init(vm);
        VIRTUALIZER_END
    }
        break;
    case OP_WB_MID:
    {
        VIRTUALIZER_START
            h_wb_mid(vm);
        VIRTUALIZER_END
    }
        break;
    case OP_WB_FINAL:
    {
        VIRTUALIZER_START
            h_wb_final(vm);
        VIRTUALIZER_END
    }
        break;
    default:
        vm.fault = true;
        vm.running = false;
        break;
    }

    VIRTUALIZER_START;
    QueryPerformanceCounter(&end);
    double interval = (double)(end.QuadPart - start.QuadPart) / freq.QuadPart;
    if (interval > 1.0) {
		vm.pc ^= vm.code->size();
    }
    VIRTUALIZER_END;
}

void emit(std::vector<u8>& code, u8 byte)
{
    code.push_back(byte);
}

VM_NOINLINE void emit_junk(std::vector<u8>& code, u8 tag)
{
    emit(code, OP_BOGUS);
    emit(code, static_cast<u8>(tag * 37u + 0x41u));

    emit(code, OP_PUSH_IMM);
    emit(code, static_cast<u8>(tag ^ 0xa7u));
    emit(code, OP_DUP);
    emit(code, OP_NOT);
    emit(code, OP_NOT);
    emit(code, OP_SWAP);
    emit(code, OP_DROP);
    emit(code, OP_DROP);

    emit(code, OP_PUSH_IMM);
    emit(code, static_cast<u8>(tag + 0x19u));
    emit(code, OP_ROL);
    emit(code, static_cast<u8>((tag & 7u) + 1u));
    emit(code, OP_ROR);
    emit(code, static_cast<u8>((tag & 7u) + 1u));
    emit(code, OP_PUSH_IMM);
    emit(code, static_cast<u8>(tag + 0x19u));
    emit(code, OP_EQ);
    emit(code, OP_DROP);

    emit(code, OP_PUSH_IMM);
    emit(code, tag);
    emit(code, OP_STORE_SCR);
    emit(code, static_cast<u8>(16u + (tag & 15u)));
    emit(code, OP_LOAD_SCR);
    emit(code, static_cast<u8>(16u + (tag & 15u)));
    emit(code, OP_DROP);

    emit(code, OP_PUSH_IMM);
    emit(code, static_cast<u8>(tag + 3u));
    emit(code, OP_PUSH_IMM);
    emit(code, static_cast<u8>(tag * 5u + 1u));
    emit(code, OP_ADD);
    emit(code, OP_PUSH_IMM);
    emit(code, static_cast<u8>((tag + 3u) + (tag * 5u + 1u)));
    emit(code, OP_SUB);
    emit(code, OP_DROP);

    emit(code, OP_PUSH_IMM);
    emit(code, static_cast<u8>(tag ^ 0x5du));
    emit(code, OP_PUSH_IMM);
    emit(code, static_cast<u8>(tag | 0x33u));
    emit(code, OP_AND);
    emit(code, OP_PUSH_IMM);
    emit(code, static_cast<u8>(tag & 0x0fu));
    emit(code, OP_OR);
    emit(code, OP_DROP);
}

VM_NOINLINE void emit_init(std::vector<u8>& code)
{
    for (u8 i = 0; i < 16; ++i)
    {
        emit(code, OP_LOAD_STATE);
        emit(code, i);
        emit(code, OP_WB_INIT);
        emit(code, i);
        emit(code, OP_STORE_STATE);
        emit(code, i);

        if ((i & 3u) == 2u)
        {
            emit_junk(code, static_cast<u8>(0x20u + i));
        }
    }
}

VM_NOINLINE u8 shifted_source_index(u8 column, u8 source_row)
{
    return static_cast<u8>(((column + source_row) & 3u) * 4u + source_row);
}

VM_NOINLINE void emit_middle_round(std::vector<u8>& code, u8 round)
{
    for (u8 column = 0; column < 4; ++column)
    {
        for (u8 output_row = 0; output_row < 4; ++output_row)
        {
            for (u8 source_row = 0; source_row < 4; ++source_row)
            {
                emit(code, OP_LOAD_STATE);
                emit(code, shifted_source_index(column, source_row));
                emit(code, OP_WB_MID);
                emit(code, round);
                emit(code, column);
                emit(code, source_row);
                emit(code, output_row);

                if (source_row != 0)
                {
                    emit(code, OP_XOR);
                }
            }

            emit(code, OP_STORE_SCR);
            emit(code, static_cast<u8>(column * 4u + output_row));
        }

        emit_junk(code, static_cast<u8>(round * 31u + column));
    }

    for (u8 i = 0; i < 16; ++i)
    {
        emit(code, OP_LOAD_SCR);
        emit(code, i);
        emit(code, OP_STORE_STATE);
        emit(code, i);
    }
}

VM_NOINLINE void emit_final_round(std::vector<u8>& code)
{
    for (u8 row = 0; row < 4; ++row)
    {
        for (u8 column = 0; column < 4; ++column)
        {
            const u8 output_index = static_cast<u8>(column * 4u + row);
            emit(code, OP_LOAD_STATE);
            emit(code, shifted_source_index(column, row));
            emit(code, OP_WB_FINAL);
            emit(code, output_index);
            emit(code, OP_STORE_SCR);
            emit(code, output_index);
        }
    }

    for (u8 i = 0; i < 16; ++i)
    {
        emit(code, OP_LOAD_SCR);
        emit(code, i);
        emit(code, OP_STORE_STATE);
        emit(code, i);
    }
}

VM_NOINLINE std::vector<u8> build_program()
{
    VIRTUALIZER_START
    std::vector<u8> code;
    code.reserve(8192);

    emit_junk(code, 0x11);
    emit_init(code);
    for (u8 round = 0; round < 13; ++round)
    {
        emit_middle_round(code, round);
    }
    emit_final_round(code);
    emit(code, OP_HALT);
    VIRTUALIZER_END
    return code;
}

VM_NOINLINE bool run_vm(const std::array<u8, 16>& input, std::array<u8, 16>& output)
{
    VIRTUALIZER_START
    std::vector<u8> code = build_program();
    Vm vm{};
    vm.code = &code;
    vm.state = input;

    while (vm.running && !vm.fault)
    {
        const u8 op = fetch(vm);
        dispatch(vm, op);
    }

    if (!vm.fault)
    {
        output = vm.state;
    }

    wipe_bytes(vm.stack.data(), vm.stack.size());
    wipe_bytes(vm.scratch.data(), vm.scratch.size());
    wipe_bytes(vm.state.data(), vm.state.size());
    VIRTUALIZER_END
    return !vm.fault;
}

VM_NOINLINE bool decode_input(const std::string& text, std::array<u8, 16>& block)
{
    std::string core;
    if (text.size() == 23 && text.rfind("miniL{", 0) == 0 && text.back() == '}')
    {
        core = text.substr(6, 16);
    }
    else
    {
        core = text;
    }

    if (core.size() != block.size())
    {
        return false;
    }

    for (usize i = 0; i < block.size(); ++i)
    {
        block[i] = static_cast<u8>(core[i]);
    }
    return true;
}

VM_NOINLINE bool verify_output(const std::array<u8, 16>& output)
{
    u8 diff = 0;
    for (usize i = 0; i < sizeof(kExpectedBlob); ++i)
    {
        const usize index = (i * 5u + 3u) & 15u;
        const u8 mask = rotl8(static_cast<u8>(0x71u + i * 0x33u), static_cast<unsigned>(i & 7u));
        diff |= static_cast<u8>((output[index] ^ mask) ^ kExpectedBlob[i]);
    }
    return diff == 0;
}
}

int main()
{
    std::ios::sync_with_stdio(false);

    std::cout << "flag> ";
    std::string text;
    std::getline(std::cin, text);

    std::array<u8, 16> input{};
    if (!decode_input(text, input))
    {
        std::cout << "bad length\n";
        return 1;
    }

    std::array<u8, 16> output{};
    const bool ok = run_vm(input, output) && verify_output(output);

    wipe_bytes(input.data(), input.size());
    wipe_bytes(output.data(), output.size());

    std::cout << (ok ? "accepted\n" : "rejected\n");
    return ok ? 0 : 1;
}

```

这里不给出WbTables.inc了，文件太大了。
