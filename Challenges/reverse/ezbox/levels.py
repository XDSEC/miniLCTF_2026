import os
import sys

# Handle PyInstaller bundle path
if getattr(sys, 'frozen', False):
    _BASE = sys._MEIPASS
else:
    _BASE = os.path.dirname(__file__)

LEVELS_DIR = os.path.join(_BASE, 'levels')

RECURSIVE_BLOCKS = set('0123456789')
ENTITY_CHARS = {'b'} | RECURSIVE_BLOCKS
TERRAIN_CHARS = {'#', '.', '=', '_'}


def sub_level_path(parent_path: str, block_id: str) -> str:
    """Hanoi mapping: block K always maps to level hK."""
    return f'h{block_id}'


def load_level_file(level_id: str) -> tuple[dict, dict, tuple]:
    filepath = os.path.join(LEVELS_DIR, f'{level_id}.txt')
    if not os.path.exists(filepath):
        raise FileNotFoundError(f'Level file not found: {filepath}')
    with open(filepath, 'r') as f:
        lines = [line.rstrip('\n') for line in f if line.strip()]
    return parse_level(lines)


def parse_level(lines: list[str]) -> tuple[dict, dict, tuple]:
    terrain = {}
    entities = {}
    player_pos = None

    for y, line in enumerate(lines):
        for x, ch in enumerate(line):
            if ch == 'p':
                player_pos = (x, y)

    for y, line in enumerate(lines):
        for x, ch in enumerate(line):
            pos = (x, y)
            if ch == 'p':
                terrain[pos] = '.'
            elif ch in ENTITY_CHARS:
                entities[pos] = ch
                terrain[pos] = '.'
            elif ch in TERRAIN_CHARS:
                terrain[pos] = ch
            else:
                terrain[pos] = '.'

    if player_pos is None:
        raise ValueError('Level has no player start position')

    return terrain, entities, player_pos


def list_levels() -> list[str]:
    """List all level IDs found in levels/ directory."""
    if not os.path.exists(LEVELS_DIR):
        return []
    levels = []
    for fname in sorted(os.listdir(LEVELS_DIR)):
        if fname.endswith('.txt'):
            levels.append(fname[:-4])
    return levels


def get_level_name(level_id: str) -> str:
    return level_id


def collect_all_context_paths() -> list[str]:
    """Generate all context paths in the Hanoi recursion tree.
    Each path is a unique completion key (e.g. 'h10', 'h10/0', 'h10/1/0').
    """
    paths = set()

    def walk(ctx: str, n: int):
        paths.add(ctx)
        for k in range(n):
            walk(f'{ctx}/{k}', k)

    walk('h10', 10)
    return sorted(paths)


def count_total_contexts(n: int = 10) -> int:
    """Total nodes in Hanoi tree of size n = 2^n."""
    total = 1
    for k in range(n):
        total += count_total_contexts(k)
    return total


def collect_all_level_ids() -> list[str]:
    """Alias for collect_all_context_paths."""
    return collect_all_context_paths()
