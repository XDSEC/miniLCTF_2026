# VectorizedMirage

本题结合了 **VEH（向量化异常处理）** 虚拟机、**XXTEA** 变体算法以及 **TEA** 算法。

## 1. 题目逻辑分析

程序主要分为两个校验阶段，Flag 长度总计为 $6 + 16 + 40 = 62$ 字节（估算）：

### 第一阶段：TEA 加密（明文逻辑）

在 `main` 函数中，输入的前 16 字节（跳过 `miniL{`）被 `encrypt` 函数处理。

- **算法**：标准 TEA。
- **Key**：`{ 0x11223344, 0x55667788, 0x99AABBCC, 0xDDEEFF00 }`
- **Delta**：`0x9e3779b9`
- **目标密文**：`result_1` 数组中的 4 个 `uint32_t`。

### 第二阶段：VEH 虚拟机 + XXTEA 变体（隐藏逻辑）

程序通过 `AddVectoredExceptionHandler` 注册了一系列异常处理函数。

- **触发点**：`main` 函数结尾的 `__debugbreak()` 触发断点异常。
- **运行机制**：由于 `before_main` 在全局初始化时执行，它向系统的异常处理链中压入了大量的指令处理器。当 `__debugbreak()` 触发后，系统会遍历执行这些处理器。
- **算法逻辑**：观察 `EMIT_XXTEA_ROUND` 宏，它实现了一个 **2 轮块（n=2）的 XXTEA**。
- **变体点**：
  - **Delta** 变为 `0xB9E1C851`。
  - **移位改变**：原本的 `z>>5 ^ y<<2` 被虚拟机指令 `VmShr5` (>>2) 和 `VmShl2` (<<5) 改变了。
  - **XOR 实现**：使用了逻辑门组合 `~(A & B) & ~(~A & ~B)` 来模拟异或。
- **校验目标**：全局变量 `results` 数组。

------

## 2. 算法细节还原

### 第一段 TEA 逆向

标准 TEA 解密即可。

### 第二段 XXTEA 变体逆向

根据 `VmShr` 和 `VmShl` 的定义：

- `VmShr5`: `a >> 2`
- `VmShl2`: `a << 5`
- `VmShr3`: `a >> 4`
- `VmShl4`: `a << 3`
- `VmShr2`: `a >> 3`

对应 XXTEA 的 `MX` 定义变为：

$$MX = ((z >> 2 \oplus y << 5) + (y >> 4 \oplus z << 3)) \oplus ((sum \oplus y) + (K[(p \& 3) \oplus e] \oplus z))$$

$e = (sum >> 3) \& 3$。

------

## 3. 解题脚本 (Python)

Python

```python
import struct

def tea_decrypt(v, k):
    v0, v1 = v[0], v[1]
    delta = 0x9e3779b9
    sum_val = (delta * 32) & 0xFFFFFFFF
    for _ in range(32):
        v1 = (v1 - (((v0 << 4) + k[2]) ^ (v0 + sum_val) ^ ((v0 >> 5) + k[3]))) & 0xFFFFFFFF
        v0 = (v0 - (((v1 << 4) + k[0]) ^ (v1 + sum_val) ^ ((v1 >> 5) + k[1]))) & 0xFFFFFFFF
        sum_val = (sum_val - delta) & 0xFFFFFFFF
    return v0, v1

def xxtea_variant_decrypt(v, k):
    # n = 2, delta = 0xB9E1C851
    delta = 0xB9E1C851
    rounds = 32
    sum_val = (rounds * delta) & 0xFFFFFFFF
    
    v0, v1 = v[0], v[1]
    
    for _ in range(rounds):
        e = (sum_val >> 3) & 3
        # 解密顺序与加密相反：先解 p=1(v1)，再解 p=0(v0)
        
        # 解 p = 1
        y = v0
        z = v1
        p = 1
        mx = (((z >> 2 ^ y << 5) + (y >> 4 ^ z << 3)) ^ ((sum_val ^ y) + (k[(p & 3) ^ e] ^ z))) & 0xFFFFFFFF
        v1 = (v1 - mx) & 0xFFFFFFFF
        
        # 解 p = 0
        y = v1
        z = v0
        p = 0
        mx = (((z >> 2 ^ y << 5) + (y >> 4 ^ z << 3)) ^ ((sum_val ^ y) + (k[(p & 3) ^ e] ^ z))) & 0xFFFFFFFF
        v0 = (v0 - mx) & 0xFFFFFFFF
        
        sum_val = (sum_val - delta) & 0xFFFFFFFF
        
    return v0, v1

# 数据准备
K = [0x11223344, 0x55667788, 0x99AABBCC, 0xDDEEFF00]

# 1. 还原第一阶段 (TEA)
res1 = [0x5c6c723e, 0xef5298d9, 0x62d93d11, 0x098a4e7f]
part1 = ""
for i in range(0, 4, 2):
    v = tea_decrypt(res1[i:i+2], K)
    part1 += struct.pack("<II", v[0], v[1]).decode()

# 2. 还原第二阶段 (XXTEA VM)
results = [2529833208, 1707418237, 3875301845, 2348577753, 
           3088034044, 1569396279, 1056408561, 4141435365, 
           1008452449, 1778196976]
part2 = ""
for i in range(0, 10, 2):
    v = xxtea_variant_decrypt(results[i:i+2], K)
    part2 += struct.pack("<II", v[0], v[1]).decode()

print(f"Flag: miniL{{{part1 + part2}}}")
```

------

## 4. 总结

1. **第一阶段**是简单的 TEA 算法，用于迷惑选手，让人以为只是普通的逆向，也用于简单的防AI。
2. **第二阶段**利用了 Windows 的 **VEH** 机制。由于 `before_main` 注册了大量 Handler，当程序执行到 `__debugbreak()` 时，会产生异常并进入这些 Handler 中执行真正的 XXTEA 加密。
3. **注意点**：XXTEA 变体中，位移参数被改成了 `>>2, <<5, >>4, <<3`，且 `Delta` 和 `e` 的计算偏移（`>>3`）均与标准算法不同。

**最终 Flag 格式为：**

```
miniL{EASY_UPX_AND_TEA___bie_xiao_ni_ye_guo_bu_liao_di_2_guan}
```

原题

```cpp
#include <windows.h>
#include <iostream>
#include <stack>
#include <vector>
#include <iomanip>


char input[128];// "miniL{EASY_UPX_AND_TEA___bie_xiao_ni_ye_guo_bu_liao_di_2_guan}";
uint32_t results[] = { 2529833208, 1707418237,
						3875301845, 2348577753,
						3088034044, 1569396279,
						1056408561, 4141435365,
						1008452449, 1778196976 };

size_t offset = 22;
volatile size_t result_offset = 0;

// --- 虚拟机状态 (VM State) ---
std::stack<uint32_t> vm_stack;

// 虚拟寄存器
uint32_t R_V0 = 0;   // 明文/密文块 0
uint32_t R_V1 = 0;   // 明文/密文块 1
uint32_t R_SUM = 0;  // 累加器 sum
uint32_t R_Y = 0;    // 临时变量 y
uint32_t R_Z = 0;    // 临时变量 z
uint32_t R_E = 0;    // 临时变量 e

// 密钥 (硬编码)
uint32_t K[4] = { 0x11223344, 0x55667788, 0x99AABBCC, 0xDDEEFF00 };
// 预期正确的密文结果 (举例)
uint32_t EXPECTED_V0 = 0x8A23B1C5;
uint32_t EXPECTED_V1 = 0x3F88E9D0;

volatile bool is_flag_correct = true;


// --- VM 指令集 (VEH Handlers) ---
#define NEXT_INST return EXCEPTION_CONTINUE_SEARCH

// 1. 寄存器交互指令
LONG CALLBACK VmPush_V0(PEXCEPTION_POINTERS p) { vm_stack.push(R_V0); NEXT_INST; }
LONG CALLBACK VmPush_V1(PEXCEPTION_POINTERS p) { vm_stack.push(R_V1); NEXT_INST; }
LONG CALLBACK VmPush_SUM(PEXCEPTION_POINTERS p) { vm_stack.push(R_SUM); NEXT_INST; }
LONG CALLBACK VmPush_Y(PEXCEPTION_POINTERS p) { vm_stack.push(R_Y); NEXT_INST; }
LONG CALLBACK VmPush_Z(PEXCEPTION_POINTERS p) { vm_stack.push(R_Z); NEXT_INST; }
LONG CALLBACK VmPush_E(PEXCEPTION_POINTERS p) { vm_stack.push(R_E); NEXT_INST; }

LONG CALLBACK VmPop_V0(PEXCEPTION_POINTERS p) { R_V0 = vm_stack.top(); vm_stack.pop(); NEXT_INST; }
LONG CALLBACK VmPop_V1(PEXCEPTION_POINTERS p) { R_V1 = vm_stack.top(); vm_stack.pop(); NEXT_INST; }
LONG CALLBACK VmPop_SUM(PEXCEPTION_POINTERS p) { R_SUM = vm_stack.top(); vm_stack.pop(); NEXT_INST; }
LONG CALLBACK VmPop_Y(PEXCEPTION_POINTERS p) { R_Y = vm_stack.top(); vm_stack.pop(); NEXT_INST; }
LONG CALLBACK VmPop_Z(PEXCEPTION_POINTERS p) { R_Z = vm_stack.top(); vm_stack.pop(); NEXT_INST; }
LONG CALLBACK VmPop_E(PEXCEPTION_POINTERS p) { R_E = vm_stack.top(); vm_stack.pop(); NEXT_INST; }

// 2. 常量指令 (为 XXTEA 定制)
LONG CALLBACK VmPush_Delta(PEXCEPTION_POINTERS p) { vm_stack.push(0xB9E1C851); NEXT_INST; }
LONG CALLBACK VmPush_3(PEXCEPTION_POINTERS p) { vm_stack.push(3); NEXT_INST; }
LONG CALLBACK VmPush_1(PEXCEPTION_POINTERS p) { vm_stack.push(1); NEXT_INST; }

// 3. 算术与逻辑指令 (注意出栈顺序：先弹的是右操作数 b，后弹的是 a)
LONG CALLBACK VmAdd(PEXCEPTION_POINTERS p) {
	uint32_t b = vm_stack.top(); vm_stack.pop();
	uint32_t a = vm_stack.top(); vm_stack.pop();
	vm_stack.push(a + b); NEXT_INST;
}
LONG CALLBACK VmNot(PEXCEPTION_POINTERS p) {
	uint32_t a = vm_stack.top(); vm_stack.pop();
	vm_stack.push(~a); NEXT_INST;
}

LONG CALLBACK VmAnd(PEXCEPTION_POINTERS p) {
	uint32_t b = vm_stack.top(); vm_stack.pop();
	uint32_t a = vm_stack.top(); vm_stack.pop();
	vm_stack.push(a & b); NEXT_INST;
}

// 辅助栈指令
LONG CALLBACK VmDup(PEXCEPTION_POINTERS p) {
	vm_stack.push(vm_stack.top()); NEXT_INST;
}

LONG CALLBACK VmSwap(PEXCEPTION_POINTERS p) {
	uint32_t b = vm_stack.top(); vm_stack.pop();
	uint32_t a = vm_stack.top(); vm_stack.pop();
	vm_stack.push(b); vm_stack.push(a); NEXT_INST;
}


// 4. 移位指令 (为绕过传参，直接硬编码 XXTEA 所需的偏移量)
LONG CALLBACK VmShr2(PEXCEPTION_POINTERS p) { uint32_t a = vm_stack.top(); vm_stack.pop(); vm_stack.push(a >> 3); NEXT_INST; }
LONG CALLBACK VmShr3(PEXCEPTION_POINTERS p) { uint32_t a = vm_stack.top(); vm_stack.pop(); vm_stack.push(a >> 4); NEXT_INST; }
LONG CALLBACK VmShr5(PEXCEPTION_POINTERS p) { uint32_t a = vm_stack.top(); vm_stack.pop(); vm_stack.push(a >> 2); NEXT_INST; }
LONG CALLBACK VmShl2(PEXCEPTION_POINTERS p) { uint32_t a = vm_stack.top(); vm_stack.pop(); vm_stack.push(a << 5); NEXT_INST; }
LONG CALLBACK VmShl4(PEXCEPTION_POINTERS p) { uint32_t a = vm_stack.top(); vm_stack.pop(); vm_stack.push(a << 3); NEXT_INST; }

// 5. 动态密钥获取：弹出一个索引 e，压入 Key[e]
LONG CALLBACK VmPush_KeyDyn(PEXCEPTION_POINTERS p) {
	uint32_t idx = vm_stack.top() & 3; vm_stack.pop();
	vm_stack.push(K[idx]); NEXT_INST;
}

// 6. 验证与结束指令
LONG CALLBACK VmCheckResult(PEXCEPTION_POINTERS p) {
	if (results[result_offset + 0] != R_V0 || results[result_offset + 1] != R_V1)
	{
		is_flag_correct = false;
	}
	result_offset += 2;
	NEXT_INST;
}

LONG CALLBACK VmEnd(PEXCEPTION_POINTERS p) {
#ifdef _WIN64
	p->ContextRecord->Rip += 1;
#else
	p->ContextRecord->Eip += 1;
#endif
	return EXCEPTION_CONTINUE_EXECUTION;
}

// --- 虚拟机"编译器" (将 XXTEA 逻辑组装成 VEH 链) ---


#define EMIT(handler) AddVectoredExceptionHandler(0, handler)

uint32_t R_T1 = 0;
uint32_t R_T2 = 0;

LONG CALLBACK VmPop_T1(PEXCEPTION_POINTERS p) { R_T1 = vm_stack.top(); vm_stack.pop(); NEXT_INST; }
LONG CALLBACK VmPop_T2(PEXCEPTION_POINTERS p) { R_T2 = vm_stack.top(); vm_stack.pop(); NEXT_INST; }
LONG CALLBACK VmPush_T1(PEXCEPTION_POINTERS p) { vm_stack.push(R_T1); NEXT_INST; }
LONG CALLBACK VmPush_T2(PEXCEPTION_POINTERS p) { vm_stack.push(R_T2); NEXT_INST; }
LONG CALLBACK VmXXT_NEXT(PEXCEPTION_POINTERS p) {
	R_V0 = *(uint32_t*)(input + offset);
	R_V1 = *(uint32_t*)(input + offset + 4);
	R_Z = R_V1;
	R_SUM = 0;
	offset += 8;
	NEXT_INST;
}

#define EMIT_VM_XOR()                                 \
    EMIT(VmPop_T2); /* 弹出 B 到 T2 */                 \
    EMIT(VmPop_T1); /* 弹出 A 到 T1 */                 \
                                                      \
    /* 计算 ~(A & B) */                               \
    EMIT(VmPush_T1);                                  \
    EMIT(VmPush_T2);                                  \
    EMIT(VmAnd);                                      \
    EMIT(VmNot);    /* 栈顶现为: ~(A & B) */           \
                                                      \
    /* 计算 ~(~A & ~B) */                             \
    EMIT(VmPush_T1);                                  \
    EMIT(VmNot);                                      \
    EMIT(VmPush_T2);                                  \
    EMIT(VmNot);                                      \
    EMIT(VmAnd);                                      \
    EMIT(VmNot);    /* 栈顶现为: ~(~A & ~B) */         \
                                                      \
    /* 两个结果求 AND */                               \
    EMIT(VmAnd);    /* 最终结果留在栈顶，完成 XOR! */

// 生成完整的一轮 (n=2) 的字节码
#define EMIT_XXTEA_ROUND()                                                      \
    /* 1. sum += DELTA */                                                       \
    EMIT(VmPush_SUM); EMIT(VmPush_Delta); EMIT(VmAdd); EMIT(VmPop_SUM);         \
                                                                                \
    /* 2. e = (sum >> 2) & 3 */                                                 \
    EMIT(VmPush_SUM); EMIT(VmShr2); EMIT(VmPush_3); EMIT(VmAnd); EMIT(VmPop_E); \
                                                                                \
    /* --- p = 0 --- */                                                         \
    /* y = v[1]; */                                                             \
    EMIT(VmPush_V1); EMIT(VmPop_Y);                                             \
    /* z = v[0] += MX; */                                                       \
                                                                                \
    /* MX */                                                                    \
    /* 公式: MX = (((z>>5 ^ y<<2) + (y>>3 ^ z<<4)) ^ ((sum^y) + (key[(p&3)^e] ^ z))) */ \
                                                                                \
    /* Part 1: (z>>5 ^ y<<2) */                                                 \
    EMIT(VmPush_Z); EMIT(VmShr5);                                               \
    EMIT(VmPush_Y); EMIT(VmShl2);                                               \
    EMIT_VM_XOR();                                                                \
                                                                                \
    /* Part 2: (y>>3 ^ z<<4) */                                                 \
    EMIT(VmPush_Y); EMIT(VmShr3);                                               \
    EMIT(VmPush_Z); EMIT(VmShl4);                                               \
    EMIT_VM_XOR();                                                                  \
                                                                                \
    EMIT(VmAdd); /* 栈顶现为 LeftSide */                                        \
                                                                                \
    /* Part 3: (sum^y) */                                                       \
    EMIT(VmPush_SUM); EMIT(VmPush_Y); EMIT_VM_XOR();                              \
                                                                                \
    /* Part 4: key[(p&3)^e] ^ z */                                              \
    EMIT(VmPush_E);                                                             \
    EMIT(VmPush_KeyDyn); /* 弹出索引，压入 key */                               \
    EMIT(VmPush_Z); EMIT_VM_XOR();                                               \
                                                                                \
    EMIT(VmAdd); /* 栈顶现为 RightSide */                                       \
                                                                                \
    EMIT_VM_XOR();  /* LeftSide ^ RightSide = MX (留在栈顶) */                     \
    /* MX */                                                                    \
                                                                                \
    EMIT(VmPush_V0); EMIT(VmAdd); EMIT(VmPop_V0); /* v0 += MX */                \
    EMIT(VmPush_V0); EMIT(VmPop_Z);               /* z = v0 */                  \
                                                                                \
    /* --- p = 1 --- */                                                         \
    /* y = v[0]; */                                                             \
    EMIT(VmPush_V0); EMIT(VmPop_Y);                                             \
    /* z = v[1] += MX; */                                                       \
    /* MX */                                                                    \
    /* 公式: MX = (((z>>5 ^ y<<2) + (y>>3 ^ z<<4)) ^ ((sum^y) + (key[(p&3)^e] ^ z))) */ \
                                                                                \
    /* Part 1: (z>>5 ^ y<<2) */                                                 \
    EMIT(VmPush_Z); EMIT(VmShr5);                                               \
    EMIT(VmPush_Y); EMIT(VmShl2);                                               \
    EMIT_VM_XOR();                                                                  \
                                                                                \
    /* Part 2: (y>>3 ^ z<<4) */                                                 \
    EMIT(VmPush_Y); EMIT(VmShr3);                                               \
    EMIT(VmPush_Z); EMIT(VmShl4);                                               \
    EMIT_VM_XOR();                                                                 \
                                                                                \
    EMIT(VmAdd); /* 栈顶现为 LeftSide */                                        \
                                                                                \
    /* Part 3: (sum^y) */                                                       \
    EMIT(VmPush_SUM); EMIT(VmPush_Y); EMIT_VM_XOR();                                \
                                                                                \
    /* Part 4: key[(p&3)^e] ^ z */                                              \
    EMIT(VmPush_E);                                                             \
    EMIT(VmPush_1); EMIT_VM_XOR();  /* p=1，所以索引是 1^e */                      \
    EMIT(VmPush_KeyDyn); /* 弹出索引，压入 key */                               \
    EMIT(VmPush_Z); EMIT_VM_XOR();                                                 \
                                                                                \
    EMIT(VmAdd); /* 栈顶现为 RightSide */                                       \
                                                                                \
    EMIT_VM_XOR();   /* LeftSide ^ RightSide = MX (留在栈顶) */                     \
    /* MX */                                                                    \
    EMIT(VmPush_V1); EMIT(VmAdd); EMIT(VmPop_V1); /* v1 += MX */                \
    EMIT(VmPush_V1); EMIT(VmPop_Z);               /* z = v1 */


int before_main()
{
	EMIT(VmXXT_NEXT);
	for (int i = 0; i < 32; i++)
	{
		EMIT_XXTEA_ROUND();
	}
	EMIT(VmCheckResult);
	EMIT(VmXXT_NEXT);
	for (int i = 0; i < 32; i++)
	{
		EMIT_XXTEA_ROUND();
	}
	EMIT(VmCheckResult);
	EMIT(VmXXT_NEXT);
	for (int i = 0; i < 32; i++)
	{
		EMIT_XXTEA_ROUND();
	}
	EMIT(VmCheckResult);
	EMIT(VmXXT_NEXT);
	for (int i = 0; i < 32; i++)
	{
		EMIT_XXTEA_ROUND();
	}
	EMIT(VmCheckResult);
	EMIT(VmXXT_NEXT);
	for (int i = 0; i < 32; i++)
	{
		EMIT_XXTEA_ROUND();
	}
	EMIT(VmCheckResult);
	EMIT(VmEnd);
	return 0;
}

int magic = before_main();

void encrypt(uint32_t* v, uint32_t* k) {

	uint32_t v0 = v[0], v1 = v[1];

	uint32_t sum = 0;
	uint32_t delta = 0x9e3779b9;
	uint32_t k0 = k[0], k1 = k[1], k2 = k[2], k3 = k[3];
	// std::cout << "Welcome to MiniLCTF2026" << std::endl;
	for (int i = 0; i < 32; i++) {
		sum += delta;
		v0 += ((v1 << 4) + k0) ^ (v1 + sum) ^ ((v1 >> 5) + k1);
		v1 += ((v0 << 4) + k2) ^ (v0 + sum) ^ ((v0 >> 5) + k3);
	}
	v[0] = v0; v[1] = v1;
}


// --- 主程序 ---
int main() {
	std::cout << "[=== MiniLCTF 2026 ===]" << std::endl;
	std::cout << "VectorizedMirage: Please Input Your Flag." << std::endl;
	std::cout << "root@xdsec ~# ";
	scanf_s("%s", input, 128);

	// 输入校验
	if (!(input[0] == 'm'
		&& input[1] == 'i'
		&& input[2] == 'n'
		&& input[3] == 'i'
		&& input[4] == 'L'
		&& input[5] == '{'
		&& !IsDebuggerPresent())
		)
	{
		std::cout << "[-] Invalid input format!" << std::endl;
		system("pause");
		return -1;
	}

	char* flag_ptr = input + 6; // 跳过 "miniL{"


	encrypt((uint32_t*)flag_ptr, K);
	encrypt((uint32_t*)(flag_ptr + 8), K);


	const uint32_t result_1[] = { 0x5c6c723e, 0xef5298d9, 0x62d93d11, 0x098a4e7f };
	if (
		*((uint32_t*)flag_ptr + 0) == result_1[0]
		&& *((uint32_t*)flag_ptr + 1) == result_1[1]
		&& *((uint32_t*)flag_ptr + 2) == result_1[2]
		&& *((uint32_t*)flag_ptr + 3) == result_1[3]
		)
	{
		is_flag_correct = true;
	}
	else {
		is_flag_correct = false;
	}

	__debugbreak();

	if (is_flag_correct)
	{
		std::cout << "Well, You made this Miracle!!!\nNow you can submit your flag.\n";
	}
	else
	{
		std::cout << "No! Flag is absolutely wrong.\n";
	}

	return 0;
}
```

