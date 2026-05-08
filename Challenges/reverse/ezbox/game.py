class Game:
    """Core game state and logic for recursive block-pushing puzzle."""

    def __init__(self):
        self.terrain: dict[tuple, str] = {}
        self.entities: dict[tuple, str] = {}
        self.player_pos: tuple = (0, 0)
        self.step_count: int = 0
        self.level_path: str = ''          # which .txt file ('h0'..'h10')
        self.context_path: str = ''        # completion key ('h10', 'h10/0', 'h10/1/0'...)
        self.level_stack: list[tuple] = []
        self.completed_hashes: dict[str, str] = {}
        self.total_steps: int = 0
        self._undo_stack: list = []
        self._level_name: str = ''

    def load_level(self, path: str, terrain: dict, entities: dict, player_pos: tuple,
                   name: str = '', context: str | None = None):
        self.level_path = path
        self._level_name = name or path
        if context is not None:
            self.context_path = context
        self.terrain = dict(terrain)
        self.entities = dict(entities)
        self.player_pos = player_pos
        self.step_count = 0
        self._undo_stack = []

    # ── queries ──────────────────────────────────────────────

    def is_wall(self, pos: tuple) -> bool:
        return self.terrain.get(pos) == '#'

    def is_recursive_block(self, pos: tuple) -> bool:
        return self.entities.get(pos, '') in '0123456789'

    def is_solid_block(self, pos: tuple) -> bool:
        return self.entities.get(pos, '') == 'b'

    def get_entity(self, pos: tuple) -> str:
        return self.entities.get(pos, '')

    def _sub_path(self, block_id: str) -> str:
        return f'{self.context_path}/{block_id}'

    def is_block_completed(self, block_id: str) -> bool:
        """A recursive block is 'completed' when its sub-level has been finished."""
        return self._sub_path(block_id) in self.completed_hashes

    def _active_recursive_blocks(self) -> set[str]:
        """Return set of recursive block IDs present in current level."""
        return {e for e in self.entities.values() if e in '0123456789'}

    # ── movement ─────────────────────────────────────────────

    def move(self, dx: int, dy: int) -> str | None:
        """Move player. Returns 'enter:ID' to enter a recursive block,
        None if move failed, '' if move succeeded."""
        px, py = self.player_pos
        tx, ty = px + dx, py + dy
        target = (tx, ty)

        if self.is_wall(target):
            return None

        entity = self.get_entity(target)

        # Empty cell
        if entity == '':
            self._save_undo()
            self._move_player_to(target)
            self.step_count += 1
            return ''

        # Solid block: try push
        if entity == 'b':
            bx, by = tx + dx, ty + dy
            behind = (bx, by)
            if not self.is_wall(behind) and self.get_entity(behind) == '':
                self._save_undo()
                del self.entities[target]
                self.entities[behind] = 'b'
                self._move_player_to(target)
                self.step_count += 1
                return ''
            return None

        # Recursive block
        if entity in '0123456789':
            if self.is_block_completed(entity):
                # Sub-level done → block behaves like a pushable box
                bx, by = tx + dx, ty + dy
                behind = (bx, by)
                if not self.is_wall(behind) and self.get_entity(behind) == '':
                    self._save_undo()
                    del self.entities[target]
                    self.entities[behind] = entity
                    self._move_player_to(target)
                    self.step_count += 1
                    return ''
                return None
            else:
                # Sub-level not done → can only enter, not push
                return f'enter:{entity}'

        return None

    # ── recursion ────────────────────────────────────────────

    def enter_block(self, block_id: str):
        """Save current state and push new context path."""
        self.level_stack.append((
            self.level_path,
            self.context_path,
            self.player_pos,
            dict(self.terrain),
            dict(self.entities),
            self._level_name,
            self.step_count,
            list(self._undo_stack),
        ))
        self.context_path = f'{self.context_path}/{block_id}'

    def exit_block(self):
        """Restore parent level state from stack."""
        if not self.level_stack:
            return False
        (self.level_path, self.context_path, self.player_pos, terrain, entities,
         self._level_name, self.step_count, self._undo_stack) = self.level_stack.pop()
        self.terrain = terrain
        self.entities = entities
        return True

    # ── completion ───────────────────────────────────────────

    def check_completion(self) -> bool:
        """Level is complete when:
        - Player is on every '=' goal
        - Every '_' goal has a block on it
        - Every recursive block's sub-level has been completed
        """
        for pos, cell in self.terrain.items():
            if cell == '=' and self.player_pos != pos:
                return False
            if cell == '_':
                ent = self.entities.get(pos)
                if ent is None or ent not in 'b0123456789':
                    return False

        # All recursive blocks in this level must have their sub-levels done
        for block_id in self._active_recursive_blocks():
            if not self.is_block_completed(block_id):
                return False

        return True

    def complete_level(self):
        """Record completion hash for current level."""
        from flag import hash_level_state
        goal_positions = sorted(
            f'{x},{y}' for (x, y), c in self.terrain.items() if c in '=_'
        )
        goals_str = ';'.join(goal_positions)
        h = hash_level_state(self.context_path, goals_str)
        self.completed_hashes[self.context_path] = h
        self.total_steps += self.step_count

    # ── undo ─────────────────────────────────────────────────

    def _save_undo(self):
        self._undo_stack.append((
            self.player_pos,
            dict(self.entities),
            self.step_count,
        ))

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        self.player_pos, entities, self.step_count = self._undo_stack.pop()
        self.entities = entities
        return True

    # ── rendering helpers ────────────────────────────────────

    def _move_player_to(self, pos: tuple):
        self.player_pos = pos

    def get_grid(self) -> dict[tuple, str]:
        """Return merged terrain + entities for rendering."""
        grid = dict(self.terrain)
        for pos, ent in self.entities.items():
            grid[pos] = ent
        px, py = self.player_pos
        grid[(px, py)] = 'p'
        return grid

    def get_bounds(self) -> tuple:
        all_positions = set(self.terrain.keys()) | set(self.entities.keys())
        all_positions.add(self.player_pos)
        if not all_positions:
            return (0, 0, 0, 0)
        xs = [p[0] for p in all_positions]
        ys = [p[1] for p in all_positions]
        return (min(xs), min(ys), max(xs), max(ys))
