"""Auto-solve the ezbox CTF challenge.

After extracting .pyc from the PyInstaller bundle and decompiling:
    uv run python solve.py

The solver works by importing game modules directly — the compiled binary
requires a PTY for interactive I/O, so direct API is the practical approach.
"""
import sys
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))


DIR_TO_KEY = {(0, -1): 'w', (0, 1): 's', (-1, 0): 'a', (1, 0): 'd'}


class Recorder:
    """Wrap Game.move to record keystrokes for binary replay."""
    def __init__(self, game):
        self._g = game; self._real = game.move; self.keys: list[str] = []
    def move(self, dx, dy):
        r = self._real(dx, dy)
        if (dx, dy) in DIR_TO_KEY: self.keys.append(DIR_TO_KEY[(dx, dy)])
        return r
    def __getattr__(self, n): return getattr(self._g, n)


def walk_to(g, tx, ty):
    px, py = g.player_pos
    while px > 1: g.move(-1, 0); px = g.player_pos[0]
    while px < 1: g.move(1, 0); px = g.player_pos[0]
    while py < ty: g.move(0, 1); py = g.player_pos[1]
    while py > ty: g.move(0, -1); py = g.player_pos[1]
    while px < tx: g.move(1, 0); px = g.player_pos[0]


def solve_level(level_id, game, context):
    from levels import load_level_file, RECURSIVE_BLOCKS

    terrain, entities, player_pos = load_level_file(level_id)
    game.load_level(level_id, terrain, entities, player_pos, level_id, context=context)

    if level_id == 'h0':
        game.move(1, 0); game.move(0, 1); game.move(1, 0)
        game.move(0, 1); game.move(0, 1)
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


def main():
    from game import Game
    from flag import try_get_flag
    game = Game(); rec = Recorder(game); game.move = rec.move  # type: ignore
    solve_level('h10', game, 'h10')
    flag = try_get_flag(game.completed_hashes, game.total_steps)
    print(f'FLAG:  {flag}')
    print(f'Steps: {game.total_steps}')
    print(f'Keys:  {len(rec.keys)}')


if __name__ == '__main__':
    main()
