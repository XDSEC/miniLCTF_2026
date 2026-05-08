import sys
import tty
import termios
from game import Game
from levels import load_level_file, sub_level_path, get_level_name, RECURSIVE_BLOCKS
from flag import try_get_flag, TOTAL_LEVELS

BLOCK_COLORS = {
    '0': '\033[31m', '1': '\033[32m', '2': '\033[33m',
    '3': '\033[34m', '4': '\033[35m', '5': '\033[36m',
    '6': '\033[91m', '7': '\033[92m', '8': '\033[93m',
    '9': '\033[94m',
}
RESET = '\033[0m'
MAIN_LEVEL = 'h10'


def getch() -> str:
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == '\x1b':
            seq = sys.stdin.read(2)
            if seq == '[A': return 'UP'
            if seq == '[B': return 'DOWN'
            if seq == '[C': return 'RIGHT'
            if seq == '[D': return 'LEFT'
            return 'ESC'
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def clear_screen():
    sys.stdout.write('\033[2J\033[H')
    sys.stdout.flush()


def render_grid(game: Game) -> str:
    min_x, min_y, max_x, max_y = game.get_bounds()
    grid = game.get_grid()
    px, py = game.player_pos

    lines = []
    for y in range(min_y, max_y + 1):
        line = ''
        for x in range(min_x, max_x + 1):
            cell = grid.get((x, y), ' ')
            if (x, y) == (px, py):
                line += '@'
            elif cell == '#':
                line += '#'
            elif cell == 'b':
                line += 'b'
            elif cell == '=':
                line += '='
            elif cell == '_':
                line += '_'
            elif cell in BLOCK_COLORS:
                line += f'{BLOCK_COLORS[cell]}{cell}{RESET}'
            else:
                line += ' '
        lines.append(line.rstrip())
    return '\n'.join(lines)


def render_hud(game: Game) -> str:
    lines = [
        f'Level: {game._level_name}  |  Steps: {game.step_count}',
        f'Completed: {len(game.completed_hashes)}/{TOTAL_LEVELS}  |  Total: {game.total_steps}',
    ]
    if game.level_stack:
        depth = len(game.level_stack)
        lines.append(f'Inside block (depth {depth}) - press E to exit')
    return '\n'.join(lines)


def run_level(game: Game, level_id: str, context: str | None = None):
    terrain, entities, player_pos = load_level_file(level_id)
    game.load_level(level_id, terrain, entities, player_pos, get_level_name(level_id), context=context)

    while True:
        clear_screen()
        print(render_grid(game))
        print()
        print(render_hud(game))
        print()
        print('WASD/Arrows: move | R: restart | Z: undo | Q: quit')
        if game.level_stack:
            print('E: exit current block')
        sys.stdout.flush()

        ch = getch().upper()

        if ch in ('W', 'UP'):
            result = game.move(0, -1)
        elif ch in ('S', 'DOWN'):
            result = game.move(0, 1)
        elif ch in ('A', 'LEFT'):
            result = game.move(-1, 0)
        elif ch in ('D', 'RIGHT'):
            result = game.move(1, 0)
        elif ch == 'R':
            terrain, entities, player_pos = load_level_file(level_id)
            game.load_level(level_id, terrain, entities, player_pos, get_level_name(level_id))
            continue
        elif ch == 'Z':
            game.undo()
            continue
        elif ch == 'E':
            if game.level_stack:
                game.exit_block()
                return 'back'
        elif ch == 'Q':
            return False
        elif ch == '\x03':
            raise KeyboardInterrupt
        else:
            continue

        if result is not None and result.startswith('enter:'):
            block_id = result.split(':')[1]
            sub_id = sub_level_path(level_id, block_id)
            game.enter_block(block_id)
            sub_result = run_level(game, sub_id)
            if sub_result == 'back':
                continue
            elif not sub_result:
                return False
            game.exit_block()

        if game.check_completion():
            game.complete_level()
            # Only show victory for the outermost level (h10)
            if len(game.completed_hashes) >= TOTAL_LEVELS:
                # h10 is done — all 1024 contexts complete
                return True
            if game.level_stack:
                # Sub-level: return silently to parent
                return True
            return True


def show_victory(game: Game):
    clear_screen()
    print('=' * 50)
    print('  ALL LEVELS COMPLETE!')
    print('=' * 50)
    print()
    flag = try_get_flag(game.completed_hashes, game.total_steps)
    if flag:
        print(f'  FLAG: {flag}')
    else:
        print('  Failed to decrypt flag.')
        print(f'  Total steps: {game.total_steps}')
        print(f'  Completed: {len(game.completed_hashes)}/{TOTAL_LEVELS}')
    print()
    print('=' * 50)


def main():
    game = Game()
    completed = run_level(game, MAIN_LEVEL, context=MAIN_LEVEL)
    if completed:
        show_victory(game)
        print()
        print('Press any key to exit...')
        sys.stdout.flush()
        getch()
    clear_screen()
    print('Goodbye!')
    sys.stdout.flush()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        clear_screen()
        print('Goodbye!')
        sys.stdout.flush()
    except FileNotFoundError as e:
        print(f'Error: {e}')
        sys.exit(1)
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)
