"""Test Hanoi: solve with context-dependent completion keys."""
from collections import deque
from game import Game
from levels import load_level_file, collect_all_context_paths, sub_level_path, RECURSIVE_BLOCKS
from flag import try_get_flag

DIRS = [(0, -1), (0, 1), (-1, 0), (1, 0)]


def bfs_solve_h0(game: Game, context: str) -> bool:
    terrain, entities, player_pos = load_level_file('h0')
    game.load_level('h0', terrain, entities, player_pos, 'h0', context=context)

    initial = (game.player_pos, frozenset(game.entities.items()))
    visited = {initial}
    queue = deque([(game.player_pos, dict(game.entities), [])])

    while queue:
        pos, ents, path = queue.popleft()
        if len(path) > 200:
            continue
        game.player_pos = pos
        game.entities = dict(ents)
        if game.check_completion():
            game.load_level('h0', terrain, entities, player_pos, 'h0', context=context)
            for dx, dy in path:
                game.move(dx, dy)
            game.complete_level()
            return True
        for dx, dy in DIRS:
            game.player_pos = pos
            game.entities = dict(ents)
            tx, ty = pos[0] + dx, pos[1] + dy
            target = (tx, ty)
            if game.is_wall(target):
                continue
            entity = game.get_entity(target)
            if entity == '':
                ns = (target, frozenset(game.entities.items()))
                if ns not in visited:
                    visited.add(ns)
                    queue.append((target, dict(game.entities), path + [(dx, dy)]))
            elif entity in 'b0123456789':
                bx, by = tx + dx, ty + dy
                behind = (bx, by)
                if not game.is_wall(behind) and game.get_entity(behind) == '':
                    new_ents = dict(ents)
                    del new_ents[target]
                    new_ents[behind] = entity
                    ns = (target, frozenset(new_ents.items()))
                    if ns not in visited:
                        visited.add(ns)
                        queue.append((target, new_ents, path + [(dx, dy)]))
    return False


def nudge(game: Game, dx: int, dy: int):
    game.move(dx, dy)


def go_to(game: Game, tx: int, ty: int):
    px, py = game.player_pos
    # Walk via x=1 column (no entities)
    while px > 1:
        nudge(game, -1, 0)
        px = game.player_pos[0]
    while px < 1:
        nudge(game, 1, 0)
        px = game.player_pos[0]
    while py < ty:
        nudge(game, 0, 1)
        py = game.player_pos[1]
    while py > ty:
        nudge(game, 0, -1)
        py = game.player_pos[1]


def solve_hanoi_direct(game: Game, level_id: str, context: str):
    """Push all blocks to goals (sub-levels pre-completed in completed_hashes)."""
    terrain, entities, player_pos = load_level_file(level_id)
    game.load_level(level_id, terrain, entities, player_pos, level_id, context=context)

    blocks = sorted(
        [(pos, ent) for pos, ent in entities.items() if ent != 'p'],
        key=lambda x: x[0][1]
    )

    eq_pos = None
    for pos, cell in terrain.items():
        if cell == '=':
            eq_pos = pos
            break

    for (bx, by), ent in blocks:
        go_to(game, 1, by)
        for _ in range(14):
            nudge(game, 1, 0)

    go_to(game, 1, eq_pos[1])
    while game.player_pos[0] < eq_pos[0] - 1:
        nudge(game, 1, 0)
    nudge(game, 1, 0)

    if game.check_completion():
        game.complete_level()
        return True
    return False


def solve_context(ctx: str, game: Game):
    """Solve a context path: load the appropriate file and complete it."""
    # Get level file from last segment of context
    last = ctx.rsplit('/', 1)[-1]
    file_id = last if last.startswith('h') else f'h{last}'

    # Determine disk count from file_id
    n_str = file_id[1:] if file_id.startswith('h') else '0'
    n = int(n_str) if n_str.isdigit() else 0
    for k in range(n):
        sub_ctx = f'{ctx}/{k}'
        if sub_ctx not in game.completed_hashes:
            solve_context(sub_ctx, game)

    # Now solve this level
    if file_id == 'h0':
        bfs_solve_h0(game, ctx)
    else:
        solve_hanoi_direct(game, file_id, ctx)


def main():
    game = Game()
    all_ctx = collect_all_context_paths()

    # Solve from root
    solve_context('h10', game)

    print(f'Completed: {len(game.completed_hashes)} / {len(all_ctx)} contexts')
    print(f'Total steps: {game.total_steps}')

    flag = try_get_flag(game.completed_hashes, game.total_steps)
    if flag:
        print(f'FLAG: {flag}')
    else:
        print('Flag decryption FAILED')
        if len(game.completed_hashes) < len(all_ctx):
            missing = set(all_ctx) - set(game.completed_hashes)
            print(f'Missing {len(missing)} contexts, e.g.: {list(missing)[:5]}')


if __name__ == '__main__':
    main()
