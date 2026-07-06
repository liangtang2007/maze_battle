from __future__ import annotations

from dataclasses import dataclass
import os
import pygame

from engine import (
    BREAKABLE_WALL,
    DANGER,
    ENDPOINT,
    FAKE_FRUIT,
    FLOOR,
    FRUIT,
    PUSHABLE_WALL,
    TRAP,
    WALL,
    FOG_HEAVY,
    FOG_LIGHT,
    FOG_NONE,
    ROLES,
    SKILLS,
    GameState,
    Player,
    manhattan,
)
from i18n import effect_name, event_text, message_text, normalize_language, role_name, role_summary, skill_name, task_name, tr


SCREEN_W = 1280
SCREEN_H = 760
GAME_H = 560
HUD_H = SCREEN_H - GAME_H
MAX_RENDERED_SKILLS = 8


COLORS = {
    "bg": (12, 14, 18),
    "panel": (26, 29, 38),
    "panel2": (34, 38, 50),
    "line": (85, 92, 108),
    "text": (235, 238, 242),
    "muted": (160, 168, 180),
    "accent": (64, 180, 255),
    "gold": (255, 214, 94),
    "good": (88, 214, 141),
    "bad": (255, 99, 99),
    "blue": (52, 132, 255),
    "orange": (255, 146, 64),
    "green": (96, 214, 126),
    "purple": (180, 118, 255),
}


CELL_COLORS = {
    FLOOR: (205, 211, 216),
    WALL: (55, 59, 68),
    BREAKABLE_WALL: (130, 92, 58),
    TRAP: (210, 64, 74),
    DANGER: (180, 74, 150),
    FRUIT: (247, 202, 70),
    FAKE_FRUIT: (255, 98, 116),
    ENDPOINT: (72, 210, 106),
    PUSHABLE_WALL: (62, 145, 156),
}

_FONT_CACHE = {}
_LANGUAGE = "en"
_CJK_FONT_PATHS = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
]


def set_language(language: str | None) -> None:
    global _LANGUAGE
    _LANGUAGE = normalize_language(language)


def current_language() -> str:
    return _LANGUAGE


def font(size: int, bold: bool = False):
    key = (_LANGUAGE, size, bold)
    if key not in _FONT_CACHE:
        font_obj = None
        if _LANGUAGE == "zh":
            for path in _CJK_FONT_PATHS:
                if os.path.exists(path):
                    font_obj = pygame.font.Font(path, size)
                    break
        if font_obj is None:
            font_obj = pygame.font.Font(None, size)
        font_obj.set_bold(bold)
        _FONT_CACHE[key] = font_obj
    return _FONT_CACHE[key]


@dataclass
class Button:
    rect: pygame.Rect
    label: str
    value: object = None
    hotkey: str | None = None
    enabled: bool = True

    def draw(self, screen, selected: bool = False) -> None:
        bg = (42, 50, 64) if self.enabled else (35, 35, 40)
        if selected:
            bg = (42, 96, 130)
        pygame.draw.rect(screen, bg, self.rect, border_radius=8)
        pygame.draw.rect(screen, COLORS["accent"] if selected else COLORS["line"], self.rect, 2, border_radius=8)
        text = self.label if not self.hotkey else f"{self.hotkey}. {self.label}"
        size = 20 if len(text) <= 18 else 17
        draw_text(screen, text, self.rect.center, size, COLORS["text"], center=True, bold=True)

    def hit(self, pos) -> bool:
        return self.enabled and self.rect.collidepoint(pos)


@dataclass
class Slider:
    rect: pygame.Rect
    label: str
    min_value: float
    max_value: float
    value: float
    step: float = 1.0

    def draw(self, screen) -> None:
        draw_text(screen, f"{self.label}: {format_slider_value(self.value, self.step)}", (self.rect.x, self.rect.y - 24), 18, COLORS["text"])
        line_y = self.rect.centery
        pygame.draw.line(screen, COLORS["line"], (self.rect.x, line_y), (self.rect.right, line_y), 5)
        ratio = (self.value - self.min_value) / max(0.001, self.max_value - self.min_value)
        knob_x = self.rect.x + int(ratio * self.rect.width)
        pygame.draw.circle(screen, COLORS["accent"], (knob_x, line_y), 11)

    def update_from_mouse(self, pos) -> None:
        ratio = (pos[0] - self.rect.x) / max(1, self.rect.width)
        value = self.min_value + max(0, min(1, ratio)) * (self.max_value - self.min_value)
        if self.step:
            value = round(value / self.step) * self.step
        self.value = max(self.min_value, min(self.max_value, value))

    def hit(self, pos) -> bool:
        return self.rect.inflate(20, 24).collidepoint(pos)


def draw_text(screen, text: str, pos, size: int = 18, color=None, center: bool = False, bold: bool = False) -> pygame.Rect:
    color = color or COLORS["text"]
    rendered = str(text)
    if not rendered:
        return pygame.Rect(pos[0], pos[1], 0, 0)
    try:
        surf = font(size, bold).render(rendered, True, color)
    except pygame.error as exc:
        if "zero width" in str(exc).lower():
            return pygame.Rect(pos[0], pos[1], 0, 0)
        raise
    rect = surf.get_rect()
    if center:
        rect.center = pos
    else:
        rect.topleft = pos
    screen.blit(surf, rect)
    return rect


def format_slider_value(value: float, step: float) -> str:
    if step >= 1:
        return str(int(value))
    return f"{value:.2f}"


def draw_title(screen, subtitle: str = "") -> None:
    screen.fill(COLORS["bg"])
    draw_text(screen, "MAZE BATTLE: IDEAL V2", (SCREEN_W // 2, 58), 42, COLORS["gold"], center=True, bold=True)
    if subtitle:
        draw_text(screen, subtitle, (SCREEN_W // 2, 104), 20, COLORS["muted"], center=True)


def draw_config_summary(screen, config, x: int, y: int) -> None:
    lang = getattr(config, "language", current_language())
    lines = [
        f"{tr('summary.size', lang)}: {config.maze_width} x {config.maze_height}",
        f"{tr('summary.loop', lang)}: {config.loop_ratio:.2f}",
        f"{tr('summary.overlap', lang)}: {int(config.overlap_rate * 100)}%",
        f"{tr('summary.fog', lang)}: {config.fog_level}",
        f"{tr('summary.players', lang)}: {config.player_count}",
        f"{tr('summary.features', lang)}: T{config.trap_level} P{config.pushable_level} D{config.danger_level} F{config.fruit_level}",
    ]
    for i, line in enumerate(lines):
        draw_text(screen, line, (x, y + i * 26), 18, COLORS["muted"])


def draw_role_card(screen, rect: pygame.Rect, role_id: str, selected: bool = False) -> None:
    role = ROLES[role_id]
    lang = current_language()
    pygame.draw.rect(screen, (32, 37, 48), rect, border_radius=8)
    pygame.draw.rect(screen, COLORS["accent"] if selected else COLORS["line"], rect, 2, border_radius=8)
    draw_text(screen, role_name(role_id, role.name, lang), (rect.x + 14, rect.y + 10), 22, COLORS["text"], bold=True)
    draw_text(screen, role_summary(role_id, role.summary, lang), (rect.x + 14, rect.y + 40), 15, COLORS["muted"])
    for i, skill_id in enumerate(role.skills):
        skill = SKILLS[skill_id]
        sy = rect.y + 70 + i * 34
        pygame.draw.rect(screen, (45, 52, 65), pygame.Rect(rect.x + 12, sy, rect.width - 24, 28), border_radius=6)
        draw_text(screen, skill_name(skill_id, skill.name, lang), (rect.x + 22, sy + 5), 15, COLORS["gold"])
        draw_text(screen, f"CD {int(skill.cooldown)}s", (rect.right - 76, sy + 5), 14, COLORS["muted"])


def draw_game(screen, state: GameState, local_pids: list[int], selected_skill: tuple[int, int] | None, mouse_cell: tuple[int, int] | None, target_pids: dict[int, int] | None = None, language: str | None = None) -> dict[int, dict[str, object]]:
    set_language(language or getattr(state.config, "language", current_language()))
    screen.fill(COLORS["bg"])
    local_pids = [pid for pid in local_pids if 0 <= pid < len(state.players)] or [0]
    viewports: dict[int, dict[str, object]] = {}
    if len(local_pids) >= 2:
        w = SCREEN_W // 2
        rects = [pygame.Rect(0, 0, w, GAME_H), pygame.Rect(w, 0, SCREEN_W - w, GAME_H)]
        for rect, pid in zip(rects, local_pids[:2]):
            viewports[pid] = draw_player_view(screen, state, pid, rect, selected_skill, mouse_cell, target_pids or {})
        pygame.draw.line(screen, COLORS["line"], (w, 0), (w, GAME_H), 2)
    else:
        pid = local_pids[0]
        viewports[pid] = draw_player_view(screen, state, pid, pygame.Rect(0, 0, SCREEN_W, GAME_H), selected_skill, mouse_cell, target_pids or {})
    show_tasks_in_panels = len(local_pids) >= 2
    if not show_tasks_in_panels:
        draw_task_overlay(screen, state, local_pids)
    draw_top_overlay(screen, state)
    draw_selected_skill_hint(screen, state, selected_skill, target_pids or {})
    draw_hud(screen, state, local_pids, selected_skill, target_pids or {}, show_tasks_in_panels)
    if state.winner_pid is not None:
        draw_result_overlay(screen, state)
    return viewports


def draw_player_view(screen, state: GameState, pid: int, rect: pygame.Rect, selected_skill, mouse_cell, target_pids: dict[int, int]) -> dict[str, object]:
    player = state.players[pid]
    maze = state.mazes[pid]
    tile = max(4, min((rect.width - 32) // maze.width, (rect.height - 44) // maze.height))
    grid_w = tile * maze.width
    grid_h = tile * maze.height
    ox = rect.x + (rect.width - grid_w) // 2
    oy = rect.y + 34 + (rect.height - 44 - grid_h) // 2
    grid_rect = pygame.Rect(ox, oy, grid_w, grid_h)

    pygame.draw.rect(screen, (18, 21, 28), rect)
    lang = current_language()
    draw_text(screen, f"{player.name}  {role_name(player.role_id, ROLES[player.role_id].name, lang)}", (rect.x + 14, rect.y + 8), 20, color_for_player(player), bold=True)

    visible = set(player.known_own_cells)
    explored = set(player.explored_own_cells)
    for y in range(maze.height):
        for x in range(maze.width):
            cell = maze.get(x, y)
            show_endpoint = state.goal_unlocked(pid) and (player.known_own_endpoint == (x, y) or player.position == (x, y))
            if cell == ENDPOINT and not show_endpoint:
                cell = FLOOR
            display_cell = FRUIT if cell == FAKE_FRUIT else cell
            cell_rect = pygame.Rect(ox + x * tile, oy + y * tile, tile, tile)
            if state.config.fog_level == FOG_HEAVY and (x, y) not in visible:
                color = (7, 8, 10)
            elif state.config.fog_level == FOG_LIGHT and (x, y) not in visible:
                if (x, y) in explored:
                    color = dim(CELL_COLORS.get(display_cell, (100, 100, 100)), 0.42)
                else:
                    color = (7, 8, 10)
            else:
                color = CELL_COLORS.get(display_cell, (120, 120, 120))
            pygame.draw.rect(screen, color, cell_rect)
            if tile >= 12:
                pygame.draw.rect(screen, (30, 34, 42), cell_rect, 1)

    if selected_skill and selected_skill[0] == pid:
        draw_skill_range(screen, state, pid, selected_skill[1], ox, oy, tile, target_pids.get(pid))
    if mouse_cell and grid_rect.collidepoint(pygame.mouse.get_pos()):
        mx, my = mouse_cell
        pygame.draw.rect(screen, COLORS["gold"], pygame.Rect(ox + mx * tile, oy + my * tile, tile, tile), 2)

    if state.config.trail_enabled:
        for tx, ty in player.trail[-40:]:
            if (tx, ty) in visible or state.config.fog_level == FOG_NONE:
                pygame.draw.circle(screen, (*color_for_player(player), 90), (ox + tx * tile + tile // 2, oy + ty * tile + tile // 2), max(2, tile // 5))

    for mark in player.marks:
        mx, my = mark
        if (mx, my) in visible or mark in explored:
            cx, cy = ox + mx * tile + tile // 2, oy + my * tile + tile // 2
            s = max(4, tile // 3)
            pygame.draw.polygon(screen, (255, 70, 230), [(cx, cy - s), (cx + s, cy), (cx, cy + s), (cx - s, cy)])

    if player.known_enemy_endpoint is not None:
        draw_enemy_goal_marker(screen, player.known_enemy_endpoint, ox, oy, tile, maze.width, maze.height)

    draw_player_token(screen, player, ox, oy, tile, outline=True)
    for other in state.players:
        if other.pid == pid:
            continue
        can_see = player.known_enemy_position_timer > 0 or (other.position in visible and not other.has_effect("hidden"))
        if can_see:
            draw_player_token(screen, other, ox, oy, tile, outline=False, hollow=True)

    draw_enemy_intel(screen, state, pid, rect)
    return {"rect": rect, "grid_rect": grid_rect, "origin": (ox, oy), "tile": tile, "pid": pid}


def draw_skill_range(screen, state: GameState, pid: int, slot: int, ox: int, oy: int, tile: int, target_pid: int | None = None) -> None:
    player = state.players[pid]
    if not (0 <= slot < len(player.skills)):
        return
    skill = SKILLS[player.skills[slot]]
    owner = state.target_maze_owner_for_skill(pid, slot, target_pid)
    origin = player.position if owner == pid else state.players[owner].position
    radius = skill.cast_range or max(state.mazes[owner].width, state.mazes[owner].height)
    surf = pygame.Surface((tile, tile), pygame.SRCALPHA)
    surf.fill((80, 200, 255, 80))
    for x, y in cells_for_draw(origin, radius, state.mazes[owner].width, state.mazes[owner].height):
        screen.blit(surf, (ox + x * tile, oy + y * tile))


def draw_enemy_goal_marker(screen, pos: tuple[int, int], ox: int, oy: int, tile: int, width: int, height: int) -> None:
    x, y = pos
    if not (0 <= x < width and 0 <= y < height):
        return
    center = (ox + x * tile + tile // 2, oy + y * tile + tile // 2)
    s = max(6, tile // 2)
    points = [(center[0], center[1] - s), (center[0] + s, center[1]), (center[0], center[1] + s), (center[0] - s, center[1])]
    pygame.draw.polygon(screen, COLORS["gold"], points, 3)
    pygame.draw.line(screen, COLORS["bad"], (center[0] - s, center[1]), (center[0] + s, center[1]), 2)
    pygame.draw.line(screen, COLORS["bad"], (center[0], center[1] - s), (center[0], center[1] + s), 2)


def draw_player_token(screen, player: Player, ox: int, oy: int, tile: int, outline: bool, hollow: bool = False) -> None:
    x, y = player.position
    center = (ox + x * tile + tile // 2, oy + y * tile + tile // 2)
    radius = max(5, tile // 2 - 1)
    if hollow:
        pygame.draw.circle(screen, color_for_player(player), center, radius, 3)
    else:
        pygame.draw.circle(screen, color_for_player(player), center, radius)
    if outline:
        pygame.draw.circle(screen, (255, 255, 255), center, radius, 2)
    else:
        pygame.draw.circle(screen, COLORS["bad"], center, radius + 2, 2)
    dx, dy = player.direction
    pygame.draw.line(screen, (255, 255, 255), center, (center[0] + dx * radius, center[1] + dy * radius), 2)


def draw_enemy_intel(screen, state: GameState, pid: int, view_rect: pygame.Rect) -> None:
    player = state.players[pid]
    enemy_pid = state.default_enemy_pid(pid)
    if enemy_pid is None:
        return
    enemy_maze = state.mazes[enemy_pid]
    mini = pygame.Rect(view_rect.right - 174, view_rect.bottom - 132, 160, 118)
    pygame.draw.rect(screen, (18, 20, 26), mini, border_radius=6)
    pygame.draw.rect(screen, COLORS["line"], mini, 1, border_radius=6)
    lang = current_language()
    draw_text(screen, tr("hud.enemy_intel", lang), (mini.x + 8, mini.y + 6), 14, COLORS["muted"])
    if not player.known_enemy_cells and not player.known_enemy_endpoint:
        draw_text(screen, tr("hud.no_scan", lang), (mini.centerx, mini.centery), 16, COLORS["muted"], center=True)
        return
    tw = max(2, (mini.width - 16) // enemy_maze.width)
    th = max(2, (mini.height - 34) // enemy_maze.height)
    tile = min(tw, th)
    ox = mini.x + 8
    oy = mini.y + 28
    for x, y in player.known_enemy_cells:
        cell = enemy_maze.get(x, y)
        color = CELL_COLORS.get(cell, (80, 80, 80))
        pygame.draw.rect(screen, color, pygame.Rect(ox + x * tile, oy + y * tile, tile, tile))
    if player.known_enemy_endpoint:
        x, y = player.known_enemy_endpoint
        pygame.draw.rect(screen, COLORS["good"], pygame.Rect(ox + x * tile, oy + y * tile, tile, tile))


def draw_top_overlay(screen, state: GameState) -> None:
    lang = current_language()
    draw_text(screen, format_time(state.time_elapsed), (SCREEN_W - 105, 12), 22, COLORS["gold"], bold=True)
    if state.start_delay_left > 0:
        draw_text(screen, f"{tr('hud.start_in', lang)} {state.start_delay_left:.1f}", (SCREEN_W // 2, 34), 30, COLORS["gold"], center=True, bold=True)
    leaderboard = sorted(state.players, key=lambda p: state.progress_percent(p.pid), reverse=True)
    x = SCREEN_W - 300
    y = 44
    board_h = 28 + len(leaderboard) * 24
    pygame.draw.rect(screen, (15, 18, 24), pygame.Rect(x - 8, y - 6, 282, board_h), border_radius=8)
    draw_text(screen, tr("hud.progress_board", lang), (x, y), 15, COLORS["muted"], bold=True)
    for i, p in enumerate(leaderboard):
        yy = y + 24 + i * 24
        required_tasks = [task for task in p.tasks.values() if task.required_for_win]
        done_required = sum(task.completed for task in required_tasks)
        text = f"{p.name}  {tr('hud.tasks', lang)} {done_required}/{len(required_tasks)}  {state.progress_percent(p.pid) * 100:>3.0f}%"
        draw_text(screen, text, (x, yy), 16, color_for_player(p))
    draw_events(screen, state, x - 8, y - 6 + board_h + 8, 282)


def draw_selected_skill_hint(screen, state: GameState, selected_skill: tuple[int, int] | None, target_pids: dict[int, int]) -> None:
    if not selected_skill:
        return
    pid, slot = selected_skill
    if not (0 <= pid < len(state.players)) or not (0 <= slot < len(state.players[pid].skills)):
        return
    lang = current_language()
    skill_id = state.players[pid].skills[slot]
    skill = SKILLS[skill_id]
    target_pid = target_pids.get(pid)
    owner = state.target_maze_owner_for_skill(pid, slot, target_pid)
    if normalize_language(lang) == "zh":
        target_text = f"P{owner + 1} 地图" if owner != pid else "己方地图"
        line1 = f"已选择：{skill_name(skill_id, skill.name, lang)}"
        if owner != pid:
            line2 = f"点击主地图坐标释放到 P{owner + 1}；Tab 切换目标。"
        else:
            line2 = f"点击 {target_text} 的合法格释放。"
    else:
        target_text = f"P{owner + 1} map" if owner != pid else "your map"
        line1 = f"Selected: {skill_name(skill_id, skill.name, lang)}"
        if owner != pid:
            line2 = f"Click a map coordinate for P{owner + 1}; Tab switches target."
        else:
            line2 = f"Click a legal cell on {target_text}."
    rect = pygame.Rect(SCREEN_W // 2 - 260, 104, 520, 58)
    surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    pygame.draw.rect(surf, (15, 18, 24, 220), surf.get_rect(), border_radius=8)
    pygame.draw.rect(surf, (*COLORS["gold"], 210), surf.get_rect(), 2, border_radius=8)
    screen.blit(surf, rect)
    draw_text(screen, line1, (rect.centerx, rect.y + 8), 17, COLORS["gold"], center=True, bold=True)
    draw_text(screen, line2, (rect.centerx, rect.y + 31), 15, COLORS["text"], center=True)


def draw_task_overlay(screen, state: GameState, local_pids: list[int]) -> None:
    lang = current_language()
    players = [state.players[pid] for pid in local_pids if 0 <= pid < len(state.players)]
    if not players:
        return
    x = 12
    y = 44
    width = 330
    block_h = 28 + 18 * 4 + 14
    height = min(GAME_H - 58, block_h * len(players) + 10)
    panel = pygame.Rect(x, y, width, height)
    pygame.draw.rect(screen, (15, 18, 24), panel, border_radius=8)
    pygame.draw.rect(screen, COLORS["line"], panel, 1, border_radius=8)
    cursor_y = y + 10
    for player in players:
        draw_text(screen, f"{player.name} {tr('hud.tasks_panel', lang)}", (x + 12, cursor_y), 15, color_for_player(player), bold=True)
        cursor_y += 24
        for task in player.tasks.values():
            if cursor_y > panel.bottom - 16:
                return
            if task.task_id in {"opponent_trap", "meet"}:
                progress = task.target_progress / max(1, task.target_count_required)
                status = tr("hud.done", lang) if task.completed else f"{task.target_progress}/{task.target_count_required}"
            else:
                progress = task.progress / max(1, task.required)
                status = tr("hud.done", lang) if task.completed else f"{task.progress}/{task.required}"
            color = COLORS["good"] if task.completed else COLORS["accent"]
            draw_text(screen, task_name(task.task_id, task.name, lang), (x + 12, cursor_y), 13, color)
            tag = tr("hud.required_short" if task.required_for_win else "hud.bonus_short", lang)
            draw_text(screen, tag, (x + 112, cursor_y), 11, COLORS["gold"] if task.required_for_win else COLORS["muted"])
            bar = pygame.Rect(x + 170, cursor_y + 5, 82, 7)
            pygame.draw.rect(screen, (48, 51, 62), bar)
            pygame.draw.rect(screen, color, pygame.Rect(bar.x, bar.y, int(bar.width * progress), bar.height))
            draw_text(screen, status, (bar.right + 8, cursor_y - 1), 12, COLORS["muted"])
            cursor_y += 18
        cursor_y += 14


def draw_hud(screen, state: GameState, local_pids: list[int], selected_skill, target_pids: dict[int, int], show_tasks: bool = False) -> None:
    hud = pygame.Rect(0, GAME_H, SCREEN_W, HUD_H)
    pygame.draw.rect(screen, COLORS["panel"], hud)
    pygame.draw.line(screen, COLORS["line"], (0, GAME_H), (SCREEN_W, GAME_H), 2)
    visible_players = [state.players[pid] for pid in local_pids if 0 <= pid < len(state.players)]
    if not visible_players:
        visible_players = state.players[:1]
    panel_w = SCREEN_W // len(visible_players)
    for i, player in enumerate(visible_players):
        rect = pygame.Rect(i * panel_w + 8, GAME_H + 8, panel_w - 16, HUD_H - 16)
        draw_player_panel(screen, state, player, rect, selected_skill, target_pids.get(player.pid), show_tasks)


def draw_player_panel(screen, state: GameState, player: Player, rect: pygame.Rect, selected_skill, target_pid: int | None, show_tasks: bool = False) -> None:
    lang = current_language()
    player.ensure_skill_slot_state()
    task_x = rect.x + max(350, rect.width - 258) if show_tasks else None
    left_area_w = max(260, task_x - rect.x - 24) if task_x is not None else rect.width - 24
    pygame.draw.rect(screen, COLORS["panel2"], rect, border_radius=8)
    pygame.draw.rect(screen, color_for_player(player), rect, 2, border_radius=8)
    draw_text(screen, f"{player.name} / {role_name(player.role_id, ROLES[player.role_id].name, lang)}", (rect.x + 12, rect.y + 8), 18, color_for_player(player), bold=True)
    if target_pid is not None and target_pid < len(state.players):
        draw_text(screen, f"{tr('hud.target', lang)}: P{target_pid + 1}", (rect.x + rect.width - 92, rect.y + 8), 14, COLORS["gold"], bold=True)
    own_goal = player.known_own_endpoint if state.goal_unlocked(player.pid) else tr("hud.locked", lang)
    draw_text(screen, f"{tr('hud.fruit', lang)} {player.fruits}/{state.config.fruit_required}   {tr('hud.goal', lang)}: {own_goal}", (rect.x + 12, rect.y + 34), 15, COLORS["text"])
    if player.known_enemy_endpoint:
        draw_text(screen, f"{tr('hud.enemy_goal', lang)}: {player.known_enemy_endpoint}", (rect.x + rect.width - 230, rect.y + 34), 14, COLORS["gold"])
    if player.status_message:
        draw_text(screen, message_text(player.status_message, lang), (rect.x + 12, rect.y + 56), 14, COLORS["bad"])

    effect_names = [effect_name(effect.effect_id, lang) for effect in player.effects]
    if effect_names:
        effect_x = rect.x + 12 if show_tasks else rect.x + rect.width // 2
        effect_y = rect.y + 72 if show_tasks and player.status_message else rect.y + 56
        draw_text(screen, f"{tr('hud.effects', lang)}: " + ", ".join(effect_names[:5]), (effect_x, effect_y), 13 if show_tasks else 14, COLORS["gold"])

    bar = pygame.Rect(rect.x + 12, rect.y + 82, left_area_w, 16)
    pygame.draw.rect(screen, (45, 48, 60), bar, border_radius=7)
    pygame.draw.rect(screen, color_for_player(player), pygame.Rect(bar.x, bar.y, int(bar.width * state.progress_percent(player.pid)), bar.height), border_radius=7)
    draw_text(screen, f"{state.progress_percent(player.pid) * 100:.0f}%", bar.center, 13, COLORS["text"], center=True)

    if show_tasks:
        draw_tasks_compact(screen, player, task_x, rect.y + 34, rect.right - task_x - 12)

    skill_label_y = rect.y + (100 if show_tasks else 108)
    draw_text(screen, tr("hud.skills", lang), (rect.x + 12, skill_label_y), 14, COLORS["muted"], bold=True)
    skill_y = rect.y + (116 if show_tasks else 126)
    key_labels = key_labels_for_player(player.pid)
    gap = 8 if show_tasks else 10
    max_slots = min(MAX_RENDERED_SKILLS, getattr(state.config, "max_visible_skill_slots", MAX_RENDERED_SKILLS))
    visible_skills = player.skills[:max_slots]
    skill_count = max(1, len(visible_skills))
    if len(player.skills) > max_slots:
        draw_text(screen, f"+{len(player.skills) - max_slots}", (rect.x + 70, skill_label_y), 13, COLORS["gold"], bold=True)
    skill_area_w = left_area_w
    columns = min(4, skill_count) if show_tasks else skill_count
    slot_w = min(150 if not show_tasks else 82, max(48 if show_tasks else 66, (skill_area_w - gap * (columns - 1)) // columns))
    slot_h = 30 if show_tasks else 46
    row_gap = 3 if show_tasks else 0
    for i, skill_id in enumerate(visible_skills):
        col = i % columns
        row = i // columns
        sx = rect.x + 12 + col * (slot_w + gap)
        sy = skill_y + row * (slot_h + row_gap)
        srect = pygame.Rect(sx, sy, slot_w, slot_h)
        selected = selected_skill == (player.pid, i)
        uses = player.skill_uses[i] if i < len(player.skill_uses) else None
        cooldown = player.cooldown_for_slot(i)
        draw_skill_slot(screen, skill_id, key_labels[i] if i < len(key_labels) else str(i + 1), srect, selected, uses, cooldown)


def draw_skill_slot(screen, skill_id: str, key: str, rect: pygame.Rect, selected: bool, uses: int | None = None, cooldown: float = 0.0) -> None:
    skill = SKILLS[skill_id]
    lang = current_language()
    ready = cooldown <= 0
    bg = (48, 88, 72) if ready else (58, 58, 70)
    if selected:
        bg = (50, 110, 145)
    pygame.draw.rect(screen, bg, rect, border_radius=8)
    pygame.draw.rect(screen, COLORS["gold"] if selected else COLORS["line"], rect, 2, border_radius=8)
    label = skill_name(skill_id, skill.name, lang)
    max_chars = 8 if rect.width < 70 else 12
    if len(label) > max_chars:
        label = label[:max_chars]
    draw_text(screen, label, (rect.centerx, rect.y + (4 if rect.height < 40 else 8)), 12 if rect.height < 40 else 13, COLORS["text"], center=True, bold=True)
    small_slot = rect.height < 34
    draw_text(screen, key, (rect.x + 6, rect.bottom - 14), 11 if small_slot else 12, COLORS["gold"], bold=True)
    cd_label = f"CD{int(skill.cooldown)}"
    draw_text(screen, cd_label, (rect.centerx, rect.bottom - 14), 10 if small_slot else 11, COLORS["muted"], center=True)
    if uses is not None:
        draw_text(screen, f"x{uses}", (rect.right - 28, rect.bottom - 14), 11 if small_slot else 12, COLORS["gold"], bold=True)
    if not ready:
        draw_text(screen, f"CD {cooldown:.0f}", rect.center, 16, COLORS["text"], center=True, bold=True)


def draw_tasks_compact(screen, player: Player, x: int, y: int, width: int) -> None:
    lang = current_language()
    draw_text(screen, tr("hud.tasks_panel", lang), (x, y), 14, COLORS["muted"], bold=True)
    ty = y + 20
    bar_w = max(58, min(78, width - 145))
    for task in player.tasks.values():
        if task.task_id in {"opponent_trap", "meet"}:
            progress = task.target_progress / max(1, task.target_count_required)
            status = tr("hud.done", lang) if task.completed else f"{task.target_progress}/{task.target_count_required}"
        else:
            progress = task.progress / max(1, task.required)
            status = tr("hud.done", lang) if task.completed else f"{task.progress}/{task.required}"
        color = COLORS["good"] if task.completed else COLORS["accent"]
        draw_text(screen, task_name(task.task_id, task.name, lang), (x, ty), 12, color)
        tag = tr("hud.required_short" if task.required_for_win else "hud.bonus_short", lang)
        draw_text(screen, tag, (x + 74, ty), 10, COLORS["gold"] if task.required_for_win else COLORS["muted"])
        bar = pygame.Rect(x + width - bar_w - 34, ty + 5, bar_w, 7)
        pygame.draw.rect(screen, (48, 51, 62), bar)
        pygame.draw.rect(screen, color, pygame.Rect(bar.x, bar.y, int(bar.width * progress), bar.height))
        draw_text(screen, status, (bar.right + 6, ty - 1), 11, COLORS["muted"])
        ty += 17


def draw_events(screen, state: GameState, x: int, y: int, width: int) -> None:
    if not state.events:
        return
    lang = current_language()
    shown = min(2, len(state.events))
    height = 12 + shown * 19
    rect = pygame.Rect(x, y, width, height)
    surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    pygame.draw.rect(surf, (15, 18, 24, 178), surf.get_rect(), border_radius=8)
    pygame.draw.rect(surf, (*COLORS["line"], 180), surf.get_rect(), 1, border_radius=8)
    screen.blit(surf, rect)
    for i, event in enumerate(state.events[:shown]):
        text = event_text(event.text, lang)
        if len(text) > 28:
            text = text[:27]
        draw_text(screen, text, (x + 10, y + 6 + i * 19), 13, COLORS["gold"])


def draw_result_overlay(screen, state: GameState) -> None:
    lang = current_language()
    overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 180))
    screen.blit(overlay, (0, 0))
    winner = state.players[state.winner_pid]
    draw_text(screen, tr("result.wins", lang, name=winner.name), (SCREEN_W // 2, SCREEN_H // 2 - 40), 54, COLORS["gold"], center=True, bold=True)
    draw_text(screen, tr("result.prompt", lang), (SCREEN_W // 2, SCREEN_H // 2 + 20), 22, COLORS["text"], center=True)


def key_labels_for_player(pid: int) -> list[str]:
    if pid == 0:
        return ["1", "2", "3", "4", "5", "6", "7", "8"]
    if pid == 1:
        return [",", ".", "/", ";", "[", "]", "-", "="]
    return ["1", "2", "3", "4", "5", "6", "7", "8"]


def color_for_player(player: Player):
    return COLORS.get(player.color_name, COLORS["accent"])


def dim(color, factor: float):
    return tuple(int(c * factor) for c in color)


def format_time(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def mouse_to_cell(viewports, pos) -> tuple[int, int, int] | None:
    for pid, data in viewports.items():
        rect = data["grid_rect"]
        if rect.collidepoint(pos):
            ox, oy = data["origin"]
            tile = data["tile"]
            x = (pos[0] - ox) // tile
            y = (pos[1] - oy) // tile
            return pid, int(x), int(y)
    return None


def cells_for_draw(origin, radius, width, height):
    ox, oy = origin
    for y in range(max(0, oy - radius), min(height, oy + radius + 1)):
        for x in range(max(0, ox - radius), min(width, ox + radius + 1)):
            if manhattan(origin, (x, y)) <= radius:
                yield x, y
