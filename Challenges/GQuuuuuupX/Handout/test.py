import gdb
import os

TARGET_BP = "*0x403650"
INPUT_FILE = "input.txt"
FLAG_PREFIX = "miniL{"
FLAG_SUFFIX = "}"
FLAG_LEN = 103

charset = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_"
known_flag = ""

def gdb_silent(command):
    return gdb.execute(command, from_tty=False, to_string=True)

gdb_silent("set pagination off")
gdb_silent("set confirm off")
gdb_silent("set verbose off")
gdb_silent("set debuginfod enabled off")
gdb_silent("set suppress-cli-notifications on")
gdb_silent("set print thread-events off")

gdb_silent("target native")
gdb_silent(f"hbreak {TARGET_BP}")
bp = gdb.breakpoints()[-1]
bp.silent = True

for i in range(FLAG_LEN):
    for c in charset:
        test_input = known_flag + c + "A" * (FLAG_LEN - 1 - i)

        with open(INPUT_FILE, "w") as f:
            f.write(FLAG_PREFIX + test_input + FLAG_SUFFIX + "\n")

        gdb_silent(f"run < {INPUT_FILE} > {os.devnull} 2>&1")

        for _ in range(i):
            gdb_silent("continue")

        rax_val = int(gdb.parse_and_eval("$rax"))

        if (rax_val & 0xFF) == 0:
            known_flag += c
            print(f"[+] pos {i:03d}: {c} -> {FLAG_PREFIX}{known_flag}{FLAG_SUFFIX}", flush=True)
            break
    else:
        print(f"[!] no candidate matched at pos {i}", flush=True)
        break

print(f"FINAL FLAG: {FLAG_PREFIX}{known_flag}{FLAG_SUFFIX}", flush=True)
