"""解法二：直接从关卡文件计算 1024 个哈希，不玩游戏。"""
import os; os.chdir(os.path.dirname(os.path.abspath(__file__)))

from levels import load_level_file, collect_all_context_paths
from flag import hash_level_state, derive_key, _decrypt_flag


def file_for_context(ctx):
    last = ctx.rsplit('/', 1)[-1]
    return last if last.startswith('h') else f'h{last}'


contexts = collect_all_context_paths()
hashes = {}
for ctx in sorted(contexts):
    terrain, _, _ = load_level_file(file_for_context(ctx))
    goals = sorted(f'{x},{y}' for (x, y), c in terrain.items() if c in '=_')
    hashes[ctx] = hash_level_state(ctx, ';'.join(goals))

key = derive_key(hashes)
print(_decrypt_flag(key))
