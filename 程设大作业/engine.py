from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque
import random
import time
from typing import Any

from i18n import normalize_language


FLOOR = 0
WALL = 1
BREAKABLE_WALL = 2
TRAP = 3
DANGER = 4
FRUIT = 5
FAKE_FRUIT = 6
ENDPOINT = 7
PUSHABLE_WALL = 8

WALKABLE = {FLOOR, TRAP, DANGER, FRUIT, FAKE_FRUIT, ENDPOINT}

FOG_HEAVY = "heavy"
FOG_LIGHT = "light"
FOG_NONE = "none"

MODE_LOCAL = "local"
MODE_HOST = "host"
MODE_JOIN = "join"


SIZE_PRESETS = {
    "small": (21, 15),
    "medium": (31, 21),
    "large": (41, 31),
}


FEATURE_LEVELS = {
    0: 0.0,
    1: 0.6,
    2: 1.0,
    3: 1.5,
}


@dataclass
class GameConfig:
    language: str = "en"
    mode: str = MODE_LOCAL
    maze_size_preset: str = "medium"
    maze_width: int = 31
    maze_height: int = 21
    loop_ratio: float = 0.12
    trap_level: int = 2
    danger_level: int = 1
    breakable_level: int = 2
    pushable_level: int = 1
    fruit_level: int = 2
    fruit_required: int = 3
    opponent_task_target_count: int = 1
    meet_target_count: int = 1
    required_task_ids: list[str] = field(default_factory=lambda: ["fruit"])
    random_bonus_tasks_enabled: bool = True
    bonus_task_slots: int = 3
    goal_unlock_requires_required_tasks: bool = True
    opponent_trap_task_mode: str = "own_trap"
    task_refresh_enabled: bool = False
    task_refresh_delay: float = 15.0
    max_visible_skill_slots: int = 8
    recalculate_paths_on_map_edit: bool = True
    overlap_rate: float = 1.0
    fog_level: str = FOG_LIGHT
    map_theme: str = "classic"
    player_count: int = 2
    collision_enabled: bool = False
    trail_enabled: bool = True
    start_delay: float = 0.0
    host: str = "127.0.0.1"
    port: int = 5555
    seed: int = 0

    def normalize(self) -> "GameConfig":
        self.language = normalize_language(self.language)
        self.maze_width = clamp_odd(self.maze_width, 21, 61)
        self.maze_height = clamp_odd(self.maze_height, 15, 41)
        if hasattr(self, "maze_complexity"):
            legacy = int(clamp(getattr(self, "maze_complexity"), 1, 5))
            self.loop_ratio = {1: 0.20, 2: 0.14, 3: 0.09, 4: 0.04, 5: 0.02}[legacy]
        self.loop_ratio = clamp(self.loop_ratio, 0.0, 0.25)
        self.trap_level = int(clamp(self.trap_level, 0, 3))
        self.danger_level = int(clamp(self.danger_level, 0, 3))
        self.breakable_level = int(clamp(self.breakable_level, 0, 3))
        self.pushable_level = int(clamp(self.pushable_level, 0, 3))
        self.fruit_level = int(clamp(self.fruit_level, 0, 3))
        self.fruit_required = int(clamp(self.fruit_required, 1, 9))
        self.opponent_task_target_count = int(clamp(self.opponent_task_target_count, 1, 3))
        self.meet_target_count = int(clamp(self.meet_target_count, 1, 3))
        if isinstance(self.required_task_ids, str):
            self.required_task_ids = [item.strip() for item in self.required_task_ids.split(",") if item.strip()]
        self.required_task_ids = [tid for tid in self.required_task_ids if tid in TASK_IDS]
        self.bonus_task_slots = int(clamp(self.bonus_task_slots, 0, 5))
        if self.opponent_trap_task_mode not in {"own_trap", "any_trap"}:
            self.opponent_trap_task_mode = "own_trap"
        self.task_refresh_delay = clamp(float(self.task_refresh_delay), 3.0, 120.0)
        self.max_visible_skill_slots = int(clamp(self.max_visible_skill_slots, 4, 10))
        self.overlap_rate = clamp(self.overlap_rate, 0.0, 1.0)
        self.player_count = int(clamp(self.player_count, 2, 4))
        self.opponent_task_target_count = min(self.opponent_task_target_count, self.player_count - 1)
        self.meet_target_count = min(self.meet_target_count, self.player_count - 1)
        if self.fog_level not in {FOG_HEAVY, FOG_LIGHT, FOG_NONE}:
            self.fog_level = FOG_LIGHT
        if not self.seed:
            self.seed = random.randint(1000, 999999)
        return self


@dataclass
class ActiveEffect:
    effect_id: str
    source_pid: int
    duration: float | None
    strength: float = 1.0
    message: str = ""

    def tick(self, dt: float) -> bool:
        if self.duration is None:
            return True
        self.duration -= dt
        return self.duration > 0


@dataclass
class MapEdit:
    x: int
    y: int
    new_cell: int
    revert_cell: int
    duration: float | None
    source_pid: int

    def tick(self, dt: float) -> bool:
        if self.duration is None:
            return True
        self.duration -= dt
        return self.duration > 0


@dataclass
class SkillDef:
    skill_id: str
    name: str
    description: str
    target_type: str
    target_maze: str
    cooldown: float
    cast_range: int = 0
    duration: float | None = 0
    strength: float = 1.0
    needs_mouse: bool = False
    permanent: bool = False
    reward_uses: int | None = None


@dataclass
class RoleDef:
    role_id: str
    name: str
    summary: str
    skills: list[str]


@dataclass
class TaskState:
    task_id: str
    name: str
    required: int
    progress: int = 0
    completed: bool = False
    reward_skill: str | None = None
    target_count_required: int = 1
    target_progress: int = 0
    reward_uses: int | None = None
    refresh_on_complete: bool = False
    refresh_timer: float = 0.0
    required_for_win: bool = True
    progress_baseline: int = 0
    target_baseline: list[int] = field(default_factory=list)


@dataclass
class EventLog:
    text: str
    timer: float = 4.0
    created_at: float = field(default_factory=time.time)


@dataclass
class Player:
    pid: int
    name: str
    color_name: str
    role_id: str
    position: tuple[int, int]
    start: tuple[int, int]
    endpoint: tuple[int, int]
    direction: tuple[int, int] = (0, 1)
    base_vision: int = 6
    move_timer: float = 0.0
    base_move_interval: float = 0.18
    fruits: int = 0
    fake_fruits_taken: int = 0
    meet_count: int = 0
    met_opponents: set[int] = field(default_factory=set)
    traps_triggered: int = 0
    trap_sources_triggered: set[int] = field(default_factory=set)
    skills: list[str] = field(default_factory=list)
    skill_uses: list[int | None] = field(default_factory=list)
    skill_cooldowns: list[float] = field(default_factory=list)
    cooldowns: dict[str, float] = field(default_factory=dict)
    effects: list[ActiveEffect] = field(default_factory=list)
    tasks: dict[str, TaskState] = field(default_factory=dict)
    trail: list[tuple[int, int]] = field(default_factory=list)
    longest_loop_length: int = 0
    unique_loop_keys: set[str] = field(default_factory=set)
    marks: set[tuple[int, int]] = field(default_factory=set)
    known_own_cells: set[tuple[int, int]] = field(default_factory=set)
    known_enemy_cells: set[tuple[int, int]] = field(default_factory=set)
    explored_own_cells: set[tuple[int, int]] = field(default_factory=set)
    known_own_endpoint: tuple[int, int] | None = None
    known_enemy_endpoint: tuple[int, int] | None = None
    known_own_endpoint_timer: float | None = None
    known_enemy_endpoint_timer: float | None = None
    known_enemy_position_timer: float = 0.0
    revealed_own_cells: set[tuple[int, int]] = field(default_factory=set)
    path_to_goal: list[tuple[int, int]] = field(default_factory=list)
    best_path_index: int = 0
    status_message: str = ""
    status_timer: float = 0.0

    def ensure_skill_slot_state(self) -> None:
        while len(self.skill_uses) < len(self.skills):
            self.skill_uses.append(None)
        if len(self.skill_uses) > len(self.skills):
            self.skill_uses = self.skill_uses[: len(self.skills)]
        while len(self.skill_cooldowns) < len(self.skills):
            skill_id = self.skills[len(self.skill_cooldowns)]
            self.skill_cooldowns.append(max(0.0, self.cooldowns.get(skill_id, 0.0)))
        if len(self.skill_cooldowns) > len(self.skills):
            self.skill_cooldowns = self.skill_cooldowns[: len(self.skills)]

    def cooldown(self, skill_id: str) -> float:
        return max(0.0, self.cooldowns.get(skill_id, 0.0))

    def cooldown_for_slot(self, slot_index: int) -> float:
        self.ensure_skill_slot_state()
        if 0 <= slot_index < len(self.skill_cooldowns):
            return max(0.0, self.skill_cooldowns[slot_index])
        return 0.0

    def has_effect(self, effect_id: str) -> bool:
        return any(e.effect_id == effect_id for e in self.effects)

    def effect_strength(self, effect_id: str, default: float = 0.0) -> float:
        values = [e.strength for e in self.effects if e.effect_id == effect_id]
        return max(values) if values else default

    def add_effect(self, effect: ActiveEffect) -> None:
        if self.has_effect("shield") and effect.effect_id in NEGATIVE_EFFECTS:
            return
        self.effects = [e for e in self.effects if e.effect_id != effect.effect_id]
        self.effects.append(effect)
        if effect.message:
            self.status_message = effect.message
            self.status_timer = effect.duration or 3.0


@dataclass
class MazeModel:
    width: int
    height: int
    grid: list[list[int]]
    map_edits: list[MapEdit] = field(default_factory=list)
    trap_sources: dict[tuple[int, int], int] = field(default_factory=dict)

    def valid(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def get(self, x: int, y: int) -> int:
        if not self.valid(x, y):
            return WALL
        return self.grid[y][x]

    def set(self, x: int, y: int, cell: int) -> None:
        if self.valid(x, y):
            self.grid[y][x] = cell

    def walkable(self, x: int, y: int) -> bool:
        return self.get(x, y) in WALKABLE

    def floors(self) -> list[tuple[int, int]]:
        return [(x, y) for y in range(self.height) for x in range(self.width) if self.walkable(x, y)]


SKILLS: dict[str, SkillDef] = {
    "reveal_own_area": SkillDef("reveal_own_area", "Own Scan", "Reveal nearby own maze walls.", "cell", "own", 18, 6, None, 5, True),
    "reveal_enemy_area": SkillDef("reveal_enemy_area", "Enemy Scan", "Reveal an area of enemy maze walls.", "cell", "enemy", 25, 6, None, 4, True),
    "reveal_enemy_pos": SkillDef("reveal_enemy_pos", "Tracker", "Show enemy position briefly.", "none", "knowledge", 22, 0, 5),
    "hide_self": SkillDef("hide_self", "Hide", "Hide your position from enemy vision.", "self", "self", 30, 0, 4),
    "reveal_own_goal": SkillDef("reveal_own_goal", "Own Goal", "Reveal your real endpoint.", "none", "knowledge", 35, 0, 20),
    "reveal_enemy_goal": SkillDef("reveal_enemy_goal", "Enemy Goal", "Reveal enemy endpoint.", "none", "knowledge", 45, 0, None),
    "break_wall": SkillDef("break_wall", "Break", "Temporarily break one wall in your maze.", "cell", "own", 18, 0, 8, 1, True),
    "perm_break": SkillDef("perm_break", "Perm Break", "Permanently break one wall in your maze.", "cell", "own", 45, 0, None, 1, True, True),
    "build_wall": SkillDef("build_wall", "Build", "Temporarily build a wall in enemy maze.", "cell", "enemy", 28, 0, 10, 1, True),
    "perm_build": SkillDef("perm_build", "Perm Build", "Permanently build a wall in enemy maze.", "cell", "enemy", 55, 0, None, 1, True, True),
    "move_enemy_goal": SkillDef("move_enemy_goal", "Move Goal", "Move enemy endpoint to a valid cell.", "cell", "enemy", 50, 0, None, 1, True),
    "blind_enemy": SkillDef("blind_enemy", "Blind", "Shrink enemy vision.", "enemy", "enemy_player", 28, 10, 5, 3),
    "fake_fruit": SkillDef("fake_fruit", "Fake", "Place fake fruit in enemy maze.", "enemy", "enemy_player", 24, 0, None, 1, False),
    "speed_up": SkillDef("speed_up", "Haste", "Move faster briefly.", "self", "self", 20, 0, 5, 1.6),
    "slow_enemy": SkillDef("slow_enemy", "Slow", "Slow enemy movement.", "enemy", "enemy_player", 25, 8, 4, 0.55),
    "confuse_enemy": SkillDef("confuse_enemy", "Reverse", "Reverse enemy controls.", "enemy", "enemy_player", 30, 8, 3),
    "trap_area": SkillDef("trap_area", "Trap", "Add a negative trap area.", "cell", "enemy", 35, 0, 10, 2, True),
    "stun_enemy": SkillDef("stun_enemy", "Bind", "Stop enemy briefly.", "enemy", "enemy_player", 35, 6, 1.5),
    "shield": SkillDef("shield", "Shield", "Immune to negative effects.", "self", "self", 40, 0, 5),
    "teleport": SkillDef("teleport", "Blink", "Teleport within range.", "cell", "own", 30, 5, None, 1, True),
    "steal": SkillDef("steal", "Steal", "Steal one fruit or skill charge at close range.", "enemy", "enemy_player", 30, 2, None),
}


ROLES: dict[str, RoleDef] = {
    "explorer": RoleDef("explorer", "Explorer", "Vision and route control.", ["reveal_own_area", "reveal_own_goal", "reveal_enemy_pos", "speed_up"]),
    "saboteur": RoleDef("saboteur", "Saboteur", "Enemy disruption and fake rewards.", ["slow_enemy", "confuse_enemy", "fake_fruit", "build_wall"]),
    "breaker": RoleDef("breaker", "Breaker", "Mobility and wall control.", ["break_wall", "teleport", "speed_up", "shield"]),
    "trapper": RoleDef("trapper", "Trapper", "Zones, traps, and stealing.", ["trap_area", "blind_enemy", "fake_fruit", "steal"]),
    "analyst": RoleDef("analyst", "Analyst", "Enemy intel and stealth.", ["reveal_enemy_area", "reveal_enemy_goal", "hide_self", "reveal_enemy_pos"]),
}


TASK_TEMPLATES = [
    ("fruit", "Collect Fruits", "fruit_required", "shield", 1, True),
    ("shape", "Make 4 Turns", 4, "reveal_enemy_area", 1, False),
    ("loop_length", "Close a Loop", 8, "speed_up", 1, False),
    ("unique_loops", "Find Unique Loops", 2, "teleport", 1, False),
    ("opponent_trap", "Trap Opponents", 1, "move_enemy_goal", "opponent_task_target_count", False),
    ("meet", "Meet Opponents", 2, "steal", "meet_target_count", False),
]

TASK_IDS = {template[0] for template in TASK_TEMPLATES}
BONUS_TASK_IDS = [template[0] for template in TASK_TEMPLATES if template[0] != "fruit"]
TASK_TEMPLATE_BY_ID = {template[0]: template for template in TASK_TEMPLATES}


NEGATIVE_EFFECTS = {"slow", "confuse", "stun", "blind"}


class GameState:
    def __init__(self, config: GameConfig, player_roles: list[str] | None = None):
        self.config = config.normalize()
        self.random = random.Random(self.config.seed)
        self.mazes: list[MazeModel] = []
        self.players: list[Player] = []
        self.events: list[EventLog] = []
        self.time_elapsed = 0.0
        self.winner_pid: int | None = None
        self.start_delay_left = self.config.start_delay
        self._meeting_pairs: set[tuple[int, int]] = set()
        self.player_roles = player_roles or ["explorer", "saboteur"]
        self._build_world()

    def _build_world(self) -> None:
        base = generate_maze(self.config, self.random)
        self.mazes = []
        for _ in range(self.config.player_count):
            self.mazes.append(create_player_maze_from_base(base, self.config, self.random))

        for pid in range(self.config.player_count):
            maze = self.mazes[pid]
            start = choose_floor_far_from_edges(maze, self.random)
            endpoint = farthest_floor(maze, start)
            role_id = self.player_roles[pid % len(self.player_roles)]
            role = ROLES.get(role_id, ROLES["explorer"])
            required_task_ids = set(self.config.required_task_ids)
            player = Player(
                pid=pid,
                name=f"P{pid + 1}",
                color_name=PLAYER_COLOR_NAMES[pid % len(PLAYER_COLOR_NAMES)],
                role_id=role.role_id,
                position=start,
                start=start,
                endpoint=endpoint,
                skills=list(role.skills),
                skill_uses=[None for _ in role.skills],
                skill_cooldowns=[0.0 for _ in role.skills],
                trail=[start],
            )
            player.tasks = self.initial_tasks(required_task_ids)
            path = bfs_path(maze.grid, start, endpoint)
            player.path_to_goal = path
            self.players.append(player)
            maze.set(endpoint[0], endpoint[1], ENDPOINT)
            self.update_player_vision(pid)

    def initial_tasks(self, required_task_ids: set[str]) -> dict[str, TaskState]:
        tasks: dict[str, TaskState] = {}
        for task_id in self.config.required_task_ids:
            template = TASK_TEMPLATE_BY_ID.get(task_id)
            if template:
                task = self.task_from_template(template, required_task_ids)
                tasks[task.task_id] = task
        if "fruit" not in tasks:
            template = TASK_TEMPLATE_BY_ID["fruit"]
            task = self.task_from_template(template, {"fruit"})
            tasks[task.task_id] = task

        if self.config.random_bonus_tasks_enabled:
            pool = [tid for tid in BONUS_TASK_IDS if tid not in tasks]
            self.random.shuffle(pool)
            chosen = pool[: self.config.bonus_task_slots]
        else:
            chosen = [tid for tid in BONUS_TASK_IDS if tid not in tasks]
        for task_id in chosen:
            task = self.task_from_template(TASK_TEMPLATE_BY_ID[task_id], required_task_ids)
            tasks[task.task_id] = task
        return tasks

    def task_from_template(self, template: tuple, required_task_ids: set[str]) -> TaskState:
        tid, name, req, reward, target_count, default_required_for_win = template
        required = getattr(self.config, req) if isinstance(req, str) else req
        target_required = getattr(self.config, target_count) if isinstance(target_count, str) else target_count
        is_required = tid in required_task_ids if required_task_ids else default_required_for_win
        return TaskState(
            tid,
            name,
            int(required),
            reward_skill=reward,
            target_count_required=int(target_required),
            reward_uses=1,
            refresh_on_complete=self.config.task_refresh_enabled,
            required_for_win=is_required,
        )

    def add_event(self, text: str) -> None:
        self.events.insert(0, EventLog(text))
        self.events = self.events[:8]

    def update(self, dt: float) -> None:
        if self.winner_pid is not None:
            return
        self.time_elapsed += dt
        if self.start_delay_left > 0:
            self.start_delay_left = max(0.0, self.start_delay_left - dt)

        changed_mazes: set[int] = set()
        for maze_pid, maze in enumerate(self.mazes):
            keep: list[MapEdit] = []
            for edit in maze.map_edits:
                if edit.tick(dt):
                    keep.append(edit)
                else:
                    maze.set(edit.x, edit.y, edit.revert_cell)
                    changed_mazes.add(maze_pid)
            maze.map_edits = keep
        if self.config.recalculate_paths_on_map_edit:
            for maze_pid in changed_mazes:
                self.recalculate_path_for_player(maze_pid)

        for player in self.players:
            player.ensure_skill_slot_state()
            player.move_timer = max(0.0, player.move_timer - dt)
            player.skill_cooldowns = [max(0.0, cooldown - dt) for cooldown in player.skill_cooldowns]
            for skill_id in list(player.cooldowns):
                player.cooldowns[skill_id] = max(0.0, player.cooldowns[skill_id] - dt)
            player.effects = [effect for effect in player.effects if effect.tick(dt)]
            player.known_enemy_position_timer = max(0.0, player.known_enemy_position_timer - dt)
            if player.known_own_endpoint_timer is not None:
                player.known_own_endpoint_timer = max(0.0, player.known_own_endpoint_timer - dt)
                if player.known_own_endpoint_timer <= 0:
                    player.known_own_endpoint = None
                    player.known_own_endpoint_timer = None
            if player.known_enemy_endpoint_timer is not None:
                player.known_enemy_endpoint_timer = max(0.0, player.known_enemy_endpoint_timer - dt)
                if player.known_enemy_endpoint_timer <= 0:
                    player.known_enemy_endpoint = None
                    player.known_enemy_endpoint_timer = None
            player.status_timer = max(0.0, player.status_timer - dt)
            if player.status_timer <= 0:
                player.status_message = ""

        for event in self.events:
            event.timer -= dt
        self.events = [e for e in self.events if e.timer > 0]

        for pid in range(len(self.players)):
            self.update_player_vision(pid)
            self.update_tasks(pid, dt)
            self.unlock_goal_if_ready(pid)
            self.update_progress(pid)
        self.update_meetings()
        self.check_winner()

    def update_player_vision(self, pid: int) -> None:
        player = self.players[pid]
        own = self.mazes[pid]
        radius = self.vision_radius(player)
        visible = cells_in_radius(player.position, radius, own.width, own.height)
        if self.config.fog_level == FOG_NONE:
            visible = {(x, y) for y in range(own.height) for x in range(own.width)}
        player.known_own_cells = visible | player.revealed_own_cells
        if self.config.fog_level == FOG_LIGHT:
            player.explored_own_cells |= visible
        elif self.config.fog_level == FOG_NONE:
            player.explored_own_cells = set(visible)

    def vision_radius(self, player: Player) -> int:
        radius = player.base_vision
        blind = player.effect_strength("blind", 0)
        if blind:
            radius = max(2, int(radius - blind))
        return radius

    def command_move(self, pid: int, dx: int, dy: int) -> bool:
        if self.winner_pid is not None or self.start_delay_left > 0:
            return False
        if pid >= len(self.players):
            return False
        player = self.players[pid]
        if player.move_timer > 0 or player.has_effect("stun"):
            return False
        if player.has_effect("confuse"):
            dx, dy = -dx, -dy
        if dx == 0 and dy == 0:
            return False
        player.direction = (dx, dy)
        nx, ny = player.position[0] + dx, player.position[1] + dy
        maze = self.mazes[pid]

        if self.config.collision_enabled:
            for other in self.players:
                if other.pid != pid and other.position == (nx, ny):
                    return False

        if not maze.walkable(nx, ny):
            if maze.get(nx, ny) == PUSHABLE_WALL:
                if self.try_push_wall(pid, nx, ny, dx, dy):
                    return False
            return False
        if (nx, ny) == player.endpoint and not self.goal_unlocked(pid):
            player.status_message = "Goal locked"
            player.status_timer = 2.0
            return False

        player.position = (nx, ny)
        player.trail.append(player.position)
        if len(player.trail) > 120:
            player.trail = player.trail[-120:]
        update_loop_stats(player)
        speed_factor = player.effect_strength("haste", 1.0)
        if player.has_effect("slow"):
            speed_factor = min(speed_factor, player.effect_strength("slow", 1.0))
        player.move_timer = player.base_move_interval / max(0.2, speed_factor)
        self.handle_cell_enter(pid, nx, ny)
        self.update_progress(pid)
        return True

    def try_push_wall(self, pid: int, x: int, y: int, dx: int, dy: int) -> bool:
        maze = self.mazes[pid]
        bx, by = x + dx, y + dy
        if maze.get(bx, by) != FLOOR:
            return False
        maze.set(bx, by, PUSHABLE_WALL)
        maze.set(x, y, FLOOR)
        if self.config.recalculate_paths_on_map_edit:
            self.recalculate_path_for_player(pid)
        self.add_event(f"P{pid + 1} pushed a wall")
        return True

    def handle_cell_enter(self, pid: int, x: int, y: int) -> None:
        player = self.players[pid]
        maze = self.mazes[pid]
        cell = maze.get(x, y)
        if cell == FRUIT:
            player.fruits += 1
            maze.set(x, y, FLOOR)
            self.add_event(f"P{pid + 1} collected fruit")
        elif cell == FAKE_FRUIT:
            player.fake_fruits_taken += 1
            player.add_effect(ActiveEffect("slow", -1, 2.0, 0.65, "Fake fruit slowed you"))
            maze.set(x, y, FLOOR)
            self.add_event(f"P{pid + 1} took fake fruit")
        elif cell == TRAP:
            player.traps_triggered += 1
            source_pid = maze.trap_sources.pop((x, y), -1)
            if source_pid >= 0:
                player.trap_sources_triggered.add(source_pid)
            player.add_effect(ActiveEffect("stun", -1, 1.5, 1.0, "Trap triggered"))
            maze.set(x, y, FLOOR)
            self.add_event(f"P{pid + 1} triggered trap")
        elif cell == DANGER:
            player.add_effect(ActiveEffect("slow", -1, 3.0, 0.65, "Danger zone"))

    def cast_skill(self, pid: int, slot_index: int, target: tuple[int, int] | None = None, target_pid: int | None = None) -> tuple[bool, str]:
        if self.winner_pid is not None or pid >= len(self.players):
            return False, "Game ended"
        player = self.players[pid]
        player.ensure_skill_slot_state()
        if not (0 <= slot_index < len(player.skills)):
            return False, "No skill in slot"
        skill_id = player.skills[slot_index]
        skill = SKILLS[skill_id]
        if player.cooldown_for_slot(slot_index) > 0:
            return False, "Skill cooling down"

        target_pid = self.resolve_target_pid(pid, target_pid)
        if target_pid is None and skill.target_type in {"enemy", "enemy_player"}:
            return False, "No target player"

        if target is None:
            target = self.default_skill_cell(pid, skill, target_pid)

        ok, reason = self.validate_skill_target(pid, skill, target, target_pid)
        if not ok:
            return False, reason

        self.apply_skill(pid, target_pid, skill, target)
        player.skill_cooldowns[slot_index] = skill.cooldown
        player.cooldowns[skill_id] = max(player.cooldowns.get(skill_id, 0.0), skill.cooldown)
        if slot_index < len(player.skill_uses) and player.skill_uses[slot_index] is not None:
            player.skill_uses[slot_index] -= 1
            if player.skill_uses[slot_index] <= 0:
                player.skills.pop(slot_index)
                player.skill_uses.pop(slot_index)
                player.skill_cooldowns.pop(slot_index)
        self.add_event(f"P{pid + 1} used {skill.name}")
        return True, skill.name

    def validate_skill_target(self, pid: int, skill: SkillDef, target: tuple[int, int] | None, target_pid: int | None) -> tuple[bool, str]:
        player = self.players[pid]
        if skill.skill_id == "reveal_own_goal" and not self.goal_unlocked(pid):
            return False, "Goal locked"
        if skill.target_type == "cell":
            if target is None:
                return False, "Need a target cell"
            maze_owner = pid if skill.target_maze == "own" else target_pid
            if maze_owner is None:
                return False, "No target maze"
            maze = self.mazes[maze_owner]
            x, y = target
            if not maze.valid(x, y):
                return False, "Out of maze"
            if self.cell_has_player(maze_owner, target) and skill.skill_id in {"build_wall", "perm_build", "fake_fruit", "trap_area", "move_enemy_goal"}:
                return False, "Target occupied"
            if skill.cast_range:
                origin = player.position if skill.target_maze == "own" else self.players[target_pid].position
                if manhattan(origin, target) > skill.cast_range:
                    return False, "Out of range"
        elif skill.target_type in {"enemy", "enemy_player"}:
            enemy = self.players[target_pid]
            if skill.cast_range and manhattan(player.position, enemy.position) > skill.cast_range:
                return False, "Enemy out of range"
        return True, "OK"

    def default_skill_cell(self, pid: int, skill: SkillDef, target_pid: int | None) -> tuple[int, int] | None:
        if skill.target_type != "cell":
            return None
        if skill.target_maze == "own":
            owner = pid
            origin = self.players[pid].position
            direction = self.players[pid].direction
        elif skill.target_maze == "enemy" and target_pid is not None:
            owner = target_pid
            origin = self.players[target_pid].position
            direction = self.players[target_pid].direction
        else:
            return None

        maze = self.mazes[owner]
        max_range = skill.cast_range or max(maze.width, maze.height)
        cells_ahead = [
            (origin[0] + direction[0] * dist, origin[1] + direction[1] * dist)
            for dist in range(1, max_range + 1)
        ]

        if skill.skill_id in {"break_wall", "perm_break"}:
            return first_cell_matching(maze, cells_ahead, {WALL, BREAKABLE_WALL, PUSHABLE_WALL})
        if skill.skill_id == "teleport":
            walkable = [cell for cell in cells_ahead if maze.walkable(*cell)]
            return walkable[-1] if walkable else None
        if skill.skill_id in {"build_wall", "perm_build"}:
            return first_cell_matching(maze, cells_ahead, {FLOOR})
        if skill.skill_id == "trap_area":
            return first_cell_matching(maze, cells_ahead, {FLOOR, TRAP, DANGER}) or origin
        if skill.skill_id == "move_enemy_goal":
            return farthest_floor(maze, self.players[target_pid].position if target_pid is not None else origin)
        if skill.skill_id == "reveal_own_area":
            return bounded_cell_ahead(origin, direction, max_range, maze)
        if skill.skill_id == "reveal_enemy_area":
            return origin
        return bounded_cell_ahead(origin, direction, max_range, maze)

    def apply_skill(self, pid: int, target_pid: int | None, skill: SkillDef, target: tuple[int, int] | None) -> None:
        player = self.players[pid]
        enemy = self.players[target_pid] if target_pid is not None else None

        if skill.skill_id == "reveal_own_area":
            cells = cells_in_radius(target, int(skill.strength), self.mazes[pid].width, self.mazes[pid].height)
            player.revealed_own_cells |= cells
            player.explored_own_cells |= cells
            player.known_own_cells |= cells
        elif skill.skill_id == "reveal_enemy_area" and enemy:
            player.known_enemy_cells |= cells_in_radius(target, int(skill.strength), self.mazes[target_pid].width, self.mazes[target_pid].height)
        elif skill.skill_id == "reveal_enemy_pos":
            player.known_enemy_position_timer = skill.duration or 5
        elif skill.skill_id == "hide_self":
            player.add_effect(ActiveEffect("hidden", pid, skill.duration, 1.0, "Hidden"))
        elif skill.skill_id == "reveal_own_goal":
            player.known_own_endpoint = player.endpoint
            player.known_own_endpoint_timer = skill.duration
        elif skill.skill_id == "reveal_enemy_goal" and enemy:
            player.known_enemy_endpoint = enemy.endpoint
            player.known_enemy_endpoint_timer = skill.duration
        elif skill.skill_id in {"break_wall", "perm_break"}:
            self.apply_map_edit(pid, target, FLOOR, None if skill.permanent else (skill.duration or 8), pid)
        elif skill.skill_id in {"build_wall", "perm_build"} and enemy:
            self.apply_map_edit(target_pid, target, WALL, skill.duration, pid)
            enemy.status_message = "Enemy built a wall"
            enemy.status_timer = 3.0
        elif skill.skill_id == "move_enemy_goal" and enemy:
            self.move_endpoint(target_pid, target, pid)
        elif skill.skill_id == "blind_enemy" and enemy:
            enemy.add_effect(ActiveEffect("blind", pid, skill.duration, skill.strength, "Vision reduced"))
        elif skill.skill_id == "fake_fruit" and enemy:
            maze = self.mazes[target_pid]
            fake_target = self.random_floor_cell(target_pid)
            if fake_target:
                maze.set(fake_target[0], fake_target[1], FAKE_FRUIT)
                enemy.status_message = "Fake fruit appeared"
                enemy.status_timer = 3.0
        elif skill.skill_id == "speed_up":
            player.add_effect(ActiveEffect("haste", pid, skill.duration, skill.strength, "Speed up"))
        elif skill.skill_id == "slow_enemy" and enemy:
            enemy.add_effect(ActiveEffect("slow", pid, skill.duration, skill.strength, "Slowed"))
        elif skill.skill_id == "confuse_enemy" and enemy:
            enemy.add_effect(ActiveEffect("confuse", pid, skill.duration, 1.0, "Controls reversed"))
        elif skill.skill_id == "trap_area" and enemy:
            self.place_area(target_pid, target, int(skill.strength), TRAP, pid)
            enemy.status_message = "Trap area placed"
            enemy.status_timer = 3.0
        elif skill.skill_id == "stun_enemy" and enemy:
            enemy.add_effect(ActiveEffect("stun", pid, skill.duration, 1.0, "Bound"))
        elif skill.skill_id == "shield":
            player.add_effect(ActiveEffect("shield", pid, skill.duration, 1.0, "Shielded"))
        elif skill.skill_id == "teleport":
            if target and self.mazes[pid].walkable(*target) and (target != player.endpoint or self.goal_unlocked(pid)):
                player.position = target
                player.trail.append(target)
            elif target == player.endpoint:
                player.status_message = "Goal locked"
                player.status_timer = 2.0
        elif skill.skill_id == "steal" and enemy:
            if enemy.fruits > 0:
                enemy.fruits -= 1
                player.fruits += 1
                enemy.status_message = "A fruit was stolen"
                enemy.status_timer = 3.0

    def apply_map_edit(self, maze_pid: int, target: tuple[int, int], new_cell: int, duration: float | None, source_pid: int) -> None:
        maze = self.mazes[maze_pid]
        x, y = target
        old = maze.get(x, y)
        if old == ENDPOINT or old == TRAP:
            return
        if new_cell == FLOOR and old not in {WALL, BREAKABLE_WALL, PUSHABLE_WALL}:
            return
        if new_cell == WALL and old != FLOOR:
            return
        maze.set(x, y, new_cell)
        if duration is not None:
            maze.map_edits.append(MapEdit(x, y, new_cell, old, duration, source_pid))
        if self.config.recalculate_paths_on_map_edit:
            self.recalculate_path_for_player(maze_pid)

    def place_area(self, maze_pid: int, center: tuple[int, int], radius: int, cell_type: int, source_pid: int = -1) -> None:
        maze = self.mazes[maze_pid]
        for x, y in cells_in_radius(center, radius, maze.width, maze.height):
            if maze.get(x, y) == FLOOR and not self.cell_has_player(maze_pid, (x, y)):
                maze.set(x, y, cell_type)
                if cell_type == TRAP and source_pid >= 0:
                    maze.trap_sources[(x, y)] = source_pid

    def random_floor_cell(self, maze_pid: int) -> tuple[int, int] | None:
        if not (0 <= maze_pid < len(self.mazes)):
            return None
        maze = self.mazes[maze_pid]
        candidates = [
            (x, y)
            for y in range(1, maze.height - 1)
            for x in range(1, maze.width - 1)
            if maze.get(x, y) == FLOOR and not self.cell_has_player(maze_pid, (x, y))
        ]
        return self.random.choice(candidates) if candidates else None

    def move_endpoint(self, target_pid: int, target: tuple[int, int], source_pid: int) -> None:
        player = self.players[target_pid]
        maze = self.mazes[target_pid]
        if not maze.walkable(*target) or manhattan(player.position, target) < 8:
            return
        old = player.endpoint
        if maze.get(*old) == ENDPOINT:
            maze.set(old[0], old[1], FLOOR)
        player.endpoint = target
        player.known_own_endpoint = None
        player.known_own_endpoint_timer = None
        maze.set(target[0], target[1], ENDPOINT)
        player.path_to_goal = bfs_path(maze.grid, player.start, target)
        player.best_path_index = 0
        player.status_message = "Your goal moved"
        player.status_timer = 4.0
        self.add_event(f"P{source_pid + 1} moved P{target_pid + 1}'s goal")

    def recalculate_path_for_player(self, pid: int) -> None:
        if not (0 <= pid < len(self.players)):
            return
        player = self.players[pid]
        maze = self.mazes[pid]
        old_progress = self.progress_percent(pid)
        path = bfs_path(maze.grid, player.start, player.endpoint)
        if not path:
            return
        player.path_to_goal = path
        player.best_path_index = min(len(path) - 1, int(old_progress * max(1, len(path) - 1)))
        self.update_progress(pid)

    def default_enemy_pid(self, pid: int) -> int | None:
        for player in self.players:
            if player.pid != pid:
                return player.pid
        return None

    def resolve_target_pid(self, pid: int, target_pid: int | None) -> int | None:
        if target_pid is not None and 0 <= target_pid < len(self.players) and target_pid != pid:
            return target_pid
        return self.default_enemy_pid(pid)

    def cell_has_player(self, maze_pid: int, pos: tuple[int, int]) -> bool:
        return 0 <= maze_pid < len(self.players) and self.players[maze_pid].position == pos

    def update_meetings(self) -> None:
        new_pairs: set[tuple[int, int]] = set()
        for i in range(len(self.players)):
            for j in range(i + 1, len(self.players)):
                if manhattan(self.players[i].position, self.players[j].position) <= 1:
                    pair = (i, j)
                    new_pairs.add(pair)
                    if pair not in self._meeting_pairs:
                        self.players[i].meet_count += 1
                        self.players[j].meet_count += 1
                        self.players[i].met_opponents.add(j)
                        self.players[j].met_opponents.add(i)
                        self.add_event(f"P{i + 1} met P{j + 1}")
        self._meeting_pairs = new_pairs

    def update_tasks(self, pid: int, dt: float = 0.0) -> None:
        player = self.players[pid]
        opponents = [p for p in self.players if p.pid != pid]
        if self.config.opponent_trap_task_mode == "any_trap":
            trapped_opponents = {p.pid for p in opponents if p.traps_triggered > 0}
        else:
            trapped_opponents = {p.pid for p in opponents if pid in p.trap_sources_triggered}
        met_opponents = set(player.met_opponents)
        for task_id, task in list(player.tasks.items()):
            if task.completed:
                should_refresh = task.refresh_on_complete or (self.config.random_bonus_tasks_enabled and not task.required_for_win)
                if should_refresh:
                    task.refresh_timer = max(0.0, task.refresh_timer - dt)
                    if task.refresh_timer <= 0:
                        self.refresh_task(player, task_id, trapped_opponents, met_opponents)
                        task = player.tasks.get(task_id)
                        if task is None:
                            continue
                    else:
                        continue
                else:
                    continue
            target_baseline = set(task.target_baseline)
            if task.task_id == "fruit":
                value = max(0, player.fruits - task.progress_baseline)
            elif task.task_id == "shape":
                value = trace_turns(player.trail[-20:])
            elif task.task_id == "loop_length":
                value = player.longest_loop_length
            elif task.task_id == "unique_loops":
                value = max(0, len(player.unique_loop_keys) - task.progress_baseline)
            elif task.task_id == "opponent_trap":
                value = len(trapped_opponents - target_baseline)
            elif task.task_id == "meet":
                value = max(0, player.meet_count - task.progress_baseline)
            else:
                value = 0
            task.progress = min(value, task.required)
            if task.task_id == "opponent_trap":
                task.target_progress = min(len(trapped_opponents - target_baseline), task.target_count_required)
                complete = task.target_progress >= task.target_count_required
            elif task.task_id == "meet":
                task.target_progress = min(len(met_opponents - target_baseline), task.target_count_required)
                complete = task.progress >= task.required and task.target_progress >= task.target_count_required
            else:
                task.target_progress = 0
                complete = task.progress >= task.required
            if complete:
                task.completed = True
                if task.refresh_on_complete or (self.config.random_bonus_tasks_enabled and not task.required_for_win):
                    task.refresh_timer = self.config.task_refresh_delay
                self.add_event(f"P{pid + 1} completed {task.name}")
                if task.reward_skill and (task.reward_uses is not None or task.reward_skill not in player.skills):
                    player.skills.append(task.reward_skill)
                    player.skill_uses.append(task.reward_uses)
                    player.skill_cooldowns.append(0.0)
                    self.add_event(f"P{pid + 1} gained {SKILLS[task.reward_skill].name}")
                self.unlock_goal_if_ready(pid)

    def refresh_task(self, player: Player, task_id: str, trapped_opponents: set[int], met_opponents: set[int]) -> None:
        task = player.tasks[task_id]
        if self.config.random_bonus_tasks_enabled and not task.required_for_win:
            active = set(player.tasks)
            candidates = [tid for tid in BONUS_TASK_IDS if tid not in active or tid == task_id]
            if candidates:
                new_task_id = self.random.choice(candidates)
                new_task = self.task_from_template(TASK_TEMPLATE_BY_ID[new_task_id], set(self.config.required_task_ids))
                self.apply_task_baseline(player, new_task, trapped_opponents, met_opponents)
                if new_task_id != task_id:
                    player.tasks.pop(task_id, None)
                player.tasks[new_task_id] = new_task
                return
        task.completed = False
        task.progress = 0
        task.target_progress = 0
        task.refresh_timer = 0.0
        self.apply_task_baseline(player, task, trapped_opponents, met_opponents)

    def apply_task_baseline(self, player: Player, task: TaskState, trapped_opponents: set[int], met_opponents: set[int]) -> None:
        if task.task_id == "fruit":
            task.progress_baseline = player.fruits
            task.target_baseline = []
        elif task.task_id == "meet":
            task.progress_baseline = player.meet_count
            task.target_baseline = sorted(met_opponents)
        elif task.task_id == "opponent_trap":
            task.progress_baseline = 0
            task.target_baseline = sorted(trapped_opponents)
        elif task.task_id == "unique_loops":
            task.progress_baseline = len(player.unique_loop_keys)
            task.target_baseline = []
        elif task.task_id == "loop_length":
            task.progress_baseline = 0
            task.target_baseline = []
        else:
            task.progress_baseline = 0
            task.target_baseline = []

    def update_progress(self, pid: int) -> None:
        player = self.players[pid]
        if not player.path_to_goal:
            return
        path_index = {pos: i for i, pos in enumerate(player.path_to_goal)}
        if player.position in path_index:
            player.best_path_index = max(player.best_path_index, path_index[player.position])
        else:
            nearest = min(path_index, key=lambda pos: manhattan(pos, player.position))
            player.best_path_index = max(player.best_path_index, path_index[nearest])

    def progress_percent(self, pid: int) -> float:
        player = self.players[pid]
        if len(player.path_to_goal) <= 1:
            return 0.0
        return clamp(player.best_path_index / (len(player.path_to_goal) - 1), 0.0, 1.0)

    def all_tasks_done(self, pid: int) -> bool:
        required_tasks = [task for task in self.players[pid].tasks.values() if task.required_for_win]
        return all(task.completed for task in required_tasks)

    def goal_unlocked(self, pid: int) -> bool:
        if not self.config.goal_unlock_requires_required_tasks:
            return True
        return self.all_tasks_done(pid)

    def unlock_goal_if_ready(self, pid: int) -> None:
        if not (0 <= pid < len(self.players)):
            return
        player = self.players[pid]
        if self.goal_unlocked(pid):
            player.known_own_endpoint = player.endpoint
            player.known_own_endpoint_timer = None

    def check_winner(self) -> None:
        for player in self.players:
            if self.goal_unlocked(player.pid) and player.position == player.endpoint:
                self.winner_pid = player.pid
                self.add_event(f"P{player.pid + 1} wins!")
                return

    def add_mark(self, pid: int, pos: tuple[int, int] | None = None) -> None:
        player = self.players[pid]
        pos = pos or player.position
        if pos in player.marks:
            player.marks.remove(pos)
        else:
            player.marks.add(pos)

    def target_maze_owner_for_skill(self, pid: int, slot_index: int, target_pid: int | None = None) -> int:
        skill_id = self.players[pid].skills[slot_index]
        skill = SKILLS[skill_id]
        if skill.target_maze == "enemy":
            enemy_pid = self.resolve_target_pid(pid, target_pid)
            return enemy_pid if enemy_pid is not None else pid
        return pid

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "config": self.config.__dict__,
            "time_elapsed": self.time_elapsed,
            "winner_pid": self.winner_pid,
            "mazes": [maze.grid for maze in self.mazes],
            "players": [player_to_dict(p, self.progress_percent(p.pid)) for p in self.players],
            "events": [e.text for e in self.events[:6]],
        }

    @classmethod
    def from_snapshot(cls, snap: dict[str, Any]) -> "GameState":
        config = GameConfig(**snap["config"]).normalize()
        state = cls.__new__(cls)
        state.config = config
        state.random = random.Random(config.seed)
        state.mazes = [MazeModel(len(grid[0]), len(grid), grid) for grid in snap["mazes"]]
        state.players = [player_from_dict(data) for data in snap["players"]]
        state.events = [EventLog(text) for text in snap.get("events", [])]
        state.time_elapsed = snap.get("time_elapsed", 0.0)
        state.winner_pid = snap.get("winner_pid")
        state.start_delay_left = 0.0
        state._meeting_pairs = set()
        state.player_roles = [p.role_id for p in state.players]
        return state


def player_to_dict(player: Player, progress: float) -> dict[str, Any]:
    return {
        "pid": player.pid,
        "name": player.name,
        "color_name": player.color_name,
        "role_id": player.role_id,
        "position": list(player.position),
        "start": list(player.start),
        "endpoint": list(player.endpoint),
        "direction": list(player.direction),
        "fruits": player.fruits,
        "meet_count": player.meet_count,
        "met_opponents": list(player.met_opponents),
        "traps_triggered": player.traps_triggered,
        "trap_sources_triggered": list(player.trap_sources_triggered),
        "skills": list(player.skills),
        "skill_uses": list(player.skill_uses),
        "skill_cooldowns": list(player.skill_cooldowns),
        "cooldowns": dict(player.cooldowns),
        "effects": [e.__dict__ for e in player.effects],
        "tasks": {tid: task.__dict__ for tid, task in player.tasks.items()},
        "trail": [list(p) for p in player.trail[-80:]],
        "longest_loop_length": player.longest_loop_length,
        "unique_loop_keys": list(player.unique_loop_keys),
        "marks": [list(p) for p in player.marks],
        "known_own_cells": [list(p) for p in player.known_own_cells],
        "revealed_own_cells": [list(p) for p in player.revealed_own_cells],
        "known_enemy_cells": [list(p) for p in player.known_enemy_cells],
        "explored_own_cells": [list(p) for p in player.explored_own_cells],
        "known_own_endpoint": list(player.known_own_endpoint) if player.known_own_endpoint else None,
        "known_enemy_endpoint": list(player.known_enemy_endpoint) if player.known_enemy_endpoint else None,
        "known_own_endpoint_timer": player.known_own_endpoint_timer,
        "known_enemy_endpoint_timer": player.known_enemy_endpoint_timer,
        "known_enemy_position_timer": player.known_enemy_position_timer,
        "path_to_goal": [list(p) for p in player.path_to_goal],
        "best_path_index": player.best_path_index,
        "status_message": player.status_message,
        "status_timer": player.status_timer,
        "progress": progress,
    }


def player_from_dict(data: dict[str, Any]) -> Player:
    player = Player(
        pid=data["pid"],
        name=data["name"],
        color_name=data["color_name"],
        role_id=data["role_id"],
        position=tuple(data["position"]),
        start=tuple(data["start"]),
        endpoint=tuple(data["endpoint"]),
        direction=tuple(data.get("direction", (0, 1))),
    )
    player.fruits = data.get("fruits", 0)
    player.meet_count = data.get("meet_count", 0)
    player.met_opponents = set(data.get("met_opponents", []))
    player.traps_triggered = data.get("traps_triggered", 0)
    player.trap_sources_triggered = set(data.get("trap_sources_triggered", []))
    player.skills = list(data.get("skills", []))
    player.skill_uses = list(data.get("skill_uses", [None for _ in player.skills]))
    player.skill_cooldowns = [float(v) for v in data.get("skill_cooldowns", [])]
    player.cooldowns = dict(data.get("cooldowns", {}))
    player.ensure_skill_slot_state()
    player.effects = [ActiveEffect(**effect) for effect in data.get("effects", [])]
    player.tasks = {tid: TaskState(**task) for tid, task in data.get("tasks", {}).items()}
    player.trail = [tuple(p) for p in data.get("trail", [])]
    player.longest_loop_length = data.get("longest_loop_length", 0)
    player.unique_loop_keys = set(data.get("unique_loop_keys", []))
    player.marks = {tuple(p) for p in data.get("marks", [])}
    player.known_own_cells = {tuple(p) for p in data.get("known_own_cells", [])}
    player.revealed_own_cells = {tuple(p) for p in data.get("revealed_own_cells", [])}
    player.known_enemy_cells = {tuple(p) for p in data.get("known_enemy_cells", [])}
    player.explored_own_cells = {tuple(p) for p in data.get("explored_own_cells", [])}
    player.known_own_endpoint = tuple(data["known_own_endpoint"]) if data.get("known_own_endpoint") else None
    player.known_enemy_endpoint = tuple(data["known_enemy_endpoint"]) if data.get("known_enemy_endpoint") else None
    player.known_own_endpoint_timer = data.get("known_own_endpoint_timer")
    player.known_enemy_endpoint_timer = data.get("known_enemy_endpoint_timer")
    player.known_enemy_position_timer = data.get("known_enemy_position_timer", 0.0)
    player.path_to_goal = [tuple(p) for p in data.get("path_to_goal", [])]
    player.best_path_index = data.get("best_path_index", 0)
    player.status_message = data.get("status_message", "")
    player.status_timer = data.get("status_timer", 0.0)
    return player


PLAYER_COLOR_NAMES = ["blue", "orange", "green", "purple"]


def generate_maze(config: GameConfig, rng: random.Random) -> MazeModel:
    width = clamp_odd(config.maze_width, 21, 61)
    height = clamp_odd(config.maze_height, 15, 41)
    grid = [[WALL for _ in range(width)] for _ in range(height)]

    def carve(x: int, y: int) -> None:
        grid[y][x] = FLOOR
        dirs = [(0, -2), (0, 2), (-2, 0), (2, 0)]
        rng.shuffle(dirs)
        for dx, dy in dirs:
            nx, ny = x + dx, y + dy
            if 0 < nx < width - 1 and 0 < ny < height - 1 and grid[ny][nx] == WALL:
                grid[y + dy // 2][x + dx // 2] = FLOOR
                carve(nx, ny)

    carve(1, 1)
    maze = MazeModel(width, height, grid)
    add_loops(maze, config.loop_ratio, rng)
    add_map_features(maze, config, rng)
    return maze


def create_player_maze_from_base(base: MazeModel, config: GameConfig, rng: random.Random) -> MazeModel:
    alt = generate_maze(config, rng)
    grid = []
    for y in range(base.height):
        row = []
        for x in range(base.width):
            row.append(base.get(x, y) if rng.random() < config.overlap_rate else alt.get(x, y))
        grid.append(row)
    return MazeModel(base.width, base.height, grid)


def add_map_features(maze: MazeModel, config: GameConfig, rng: random.Random) -> None:
    area = maze.width * maze.height
    fruit_count = int(4 + area * 0.010 * FEATURE_LEVELS[config.fruit_level])
    pushable_count = int(area * 0.006 * FEATURE_LEVELS[config.pushable_level])
    trap_count = int(area * 0.008 * FEATURE_LEVELS[config.trap_level])
    danger_count = int(area * 0.003 * FEATURE_LEVELS[config.danger_level])
    add_special_cells(maze, PUSHABLE_WALL, pushable_count, rng, wall_only=True)
    add_special_cells(maze, FRUIT, fruit_count, rng)
    add_special_cells(maze, TRAP, trap_count, rng)
    add_special_cells(maze, DANGER, danger_count, rng)


def add_loops(maze: MazeModel, ratio: float, rng: random.Random) -> None:
    walls = [
        (x, y) for y in range(1, maze.height - 1) for x in range(1, maze.width - 1)
        if maze.get(x, y) == WALL and (
            (maze.walkable(x - 1, y) and maze.walkable(x + 1, y)) or
            (maze.walkable(x, y - 1) and maze.walkable(x, y + 1))
        )
    ]
    rng.shuffle(walls)
    for x, y in walls[: int(len(walls) * ratio)]:
        maze.set(x, y, FLOOR)


def add_special_cells(maze: MazeModel, cell: int, count: int, rng: random.Random, wall_only: bool = False) -> None:
    if wall_only:
        choices = [(x, y) for y in range(1, maze.height - 1) for x in range(1, maze.width - 1) if maze.get(x, y) == WALL]
    else:
        choices = [(x, y) for y in range(1, maze.height - 1) for x in range(1, maze.width - 1) if maze.get(x, y) == FLOOR]
    rng.shuffle(choices)
    for x, y in choices[:count]:
        maze.set(x, y, cell)


def apply_overlap(base: MazeModel, other: MazeModel, overlap: float, rng: random.Random) -> None:
    for y in range(base.height):
        for x in range(base.width):
            if rng.random() < overlap:
                other.set(x, y, base.get(x, y))


def choose_floor_far_from_edges(maze: MazeModel, rng: random.Random) -> tuple[int, int]:
    floors = [(x, y) for x, y in maze.floors() if 2 <= x < maze.width - 2 and 2 <= y < maze.height - 2]
    return rng.choice(floors or maze.floors())


def farthest_floor(maze: MazeModel, start: tuple[int, int]) -> tuple[int, int]:
    distances = bfs_distances(maze.grid, start)
    if not distances:
        return start
    return max(distances, key=distances.get)


def bfs_distances(grid: list[list[int]], start: tuple[int, int]) -> dict[tuple[int, int], int]:
    width, height = len(grid[0]), len(grid)
    q = deque([start])
    dist = {start: 0}
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if grid[ny][nx] not in WALKABLE:
                continue
            if (nx, ny) not in dist:
                dist[(nx, ny)] = dist[(x, y)] + 1
                q.append((nx, ny))
    return dist


def bfs_path(grid: list[list[int]], start: tuple[int, int], goal: tuple[int, int]) -> list[tuple[int, int]]:
    width, height = len(grid[0]), len(grid)
    q = deque([start])
    came = {start: None}
    while q:
        x, y = q.popleft()
        if (x, y) == goal:
            break
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if grid[ny][nx] not in WALKABLE:
                continue
            if (nx, ny) not in came:
                came[(nx, ny)] = (x, y)
                q.append((nx, ny))
    if goal not in came:
        return [start]
    path = []
    cur = goal
    while cur is not None:
        path.append(cur)
        cur = came[cur]
    return list(reversed(path))


def cells_in_radius(center: tuple[int, int], radius: int, width: int, height: int) -> set[tuple[int, int]]:
    cx, cy = center
    cells = set()
    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            if 0 <= x < width and 0 <= y < height and manhattan((cx, cy), (x, y)) <= radius:
                cells.add((x, y))
    return cells


def first_cell_matching(maze: MazeModel, cells: list[tuple[int, int]], allowed: set[int]) -> tuple[int, int] | None:
    for x, y in cells:
        if maze.valid(x, y) and maze.get(x, y) in allowed:
            return (x, y)
    return None


def bounded_cell_ahead(origin: tuple[int, int], direction: tuple[int, int], distance: int, maze: MazeModel) -> tuple[int, int]:
    x = int(clamp(origin[0] + direction[0] * distance, 0, maze.width - 1))
    y = int(clamp(origin[1] + direction[1] * distance, 0, maze.height - 1))
    return (x, y)


def trace_turns(trail: list[tuple[int, int]]) -> int:
    turns = 0
    for i in range(2, len(trail)):
        a = (trail[i - 1][0] - trail[i - 2][0], trail[i - 1][1] - trail[i - 2][1])
        b = (trail[i][0] - trail[i - 1][0], trail[i][1] - trail[i - 1][1])
        if a != (0, 0) and b != (0, 0) and a != b:
            turns += 1
    return turns


def update_loop_stats(player: Player) -> None:
    for length, key in trail_loops(player.trail):
        player.longest_loop_length = max(player.longest_loop_length, length)
        player.unique_loop_keys.add(key)


def trail_loops(trail: list[tuple[int, int]], min_length: int = 4) -> list[tuple[int, str]]:
    seen: dict[tuple[int, int], list[int]] = {}
    loops: list[tuple[int, str]] = []
    for i, pos in enumerate(trail):
        for start in seen.get(pos, []):
            length = i - start
            if length >= min_length:
                loops.append((length, canonical_loop_key(trail[start:i])))
        seen.setdefault(pos, []).append(i)
    return loops


def canonical_loop_key(loop: list[tuple[int, int]]) -> str:
    if not loop:
        return ""
    variants: list[list[tuple[int, int]]] = []
    for seq in (list(loop), list(reversed(loop))):
        for i in range(len(seq)):
            variants.append(seq[i:] + seq[:i])
    canonical = min(variants)
    return ";".join(f"{x},{y}" for x, y in canonical)


def manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def clamp_odd(value: int, low: int, high: int) -> int:
    value = int(clamp(value, low, high))
    if value % 2 == 0:
        value += 1
    return int(clamp(value, low, high if high % 2 == 1 else high - 1))
