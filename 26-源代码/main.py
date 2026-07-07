from __future__ import annotations

import argparse
import sys
import pygame

from engine import (
    FOG_HEAVY,
    FOG_LIGHT,
    FOG_NONE,
    MODE_HOST,
    MODE_JOIN,
    MODE_LOCAL,
    ROLES,
    SKILLS,
    GameConfig,
    GameState,
)
from i18n import normalize_language, role_name, role_summary, tr
from netplay import ClientSession, HostSession, apply_input
from ui import (
    SCREEN_H,
    SCREEN_W,
    Button,
    Slider,
    COLORS,
    draw_config_summary,
    draw_game,
    draw_role_card,
    draw_text,
    draw_title,
    mouse_to_cell,
    set_language,
)


STATE_START = "start"
STATE_CONFIG = "config"
STATE_ROLES = "roles"
STATE_JOIN = "join"
STATE_GUIDE = "guide"
STATE_PLAYING = "playing"


class MazeBattleApp:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("Maze Battle Ideal V2")
        self.clock = pygame.time.Clock()
        self.running = True
        self.screen_state = STATE_START

        self.config = GameConfig().normalize()
        set_language(self.config.language)
        self.roles = ["explorer", "saboteur", "breaker", "analyst"]
        self.role_select_pid = 0
        self.join_host_text = "127.0.0.1"
        self.join_role = "explorer"

        self.buttons: list[Button] = []
        self.sliders: dict[str, Slider] = {}
        self.active_slider: str | None = None

        self.game_state: GameState | None = None
        self.host_session: HostSession | None = None
        self.client_session: ClientSession | None = None
        self.local_pids: list[int] = [0, 1]
        self.selected_skill: tuple[int, int] | None = None
        self.target_pids: dict[int, int] = {0: 1, 1: 0}
        self.last_viewports = {}

    def t(self, key: str, fallback: str | None = None, **kwargs) -> str:
        return tr(key, self.config.language, fallback, **kwargs)

    def set_language(self, language: str) -> None:
        self.config.language = normalize_language(language)
        set_language(self.config.language)

    def is_network_mode(self) -> bool:
        return self.config.mode in {MODE_HOST, MODE_JOIN}

    def run(self):
        while self.running:
            dt = self.clock.tick(60) / 1000.0
            self.handle_events()
            self.update(dt)
            self.draw()
            pygame.display.flip()
        self.shutdown()

    def shutdown(self):
        if self.host_session:
            self.host_session.stop()
        if self.client_session:
            self.client_session.disconnect()
        pygame.quit()

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                self.handle_keydown(event)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self.handle_mouse_down(event)
            elif event.type == pygame.MOUSEBUTTONUP:
                self.active_slider = None
            elif event.type == pygame.MOUSEMOTION:
                self.handle_mouse_motion(event)

    def handle_keydown(self, event):
        if event.key == pygame.K_ESCAPE:
            if self.screen_state == STATE_PLAYING:
                self.return_to_menu()
            elif self.screen_state != STATE_START:
                self.screen_state = STATE_START
            else:
                self.running = False
            return

        if self.screen_state == STATE_START:
            if event.key == pygame.K_1:
                self.open_config(MODE_LOCAL)
            elif event.key == pygame.K_2:
                self.open_config(MODE_HOST)
            elif event.key == pygame.K_3:
                self.screen_state = STATE_JOIN
            elif event.key == pygame.K_h:
                self.screen_state = STATE_GUIDE
            elif event.key == pygame.K_q:
                self.running = False
            elif event.key == pygame.K_e:
                self.set_language("en")
            elif event.key == pygame.K_c:
                self.set_language("zh")
        elif self.screen_state == STATE_CONFIG:
            if event.key == pygame.K_RETURN:
                self.screen_state = STATE_ROLES
        elif self.screen_state == STATE_ROLES:
            selectable_count = 1 if self.config.mode == MODE_HOST else self.config.player_count
            if pygame.K_1 <= event.key < pygame.K_1 + selectable_count:
                self.role_select_pid = event.key - pygame.K_1
            elif event.key == pygame.K_RETURN:
                self.start_game_from_config()
        elif self.screen_state == STATE_JOIN:
            self.handle_join_key(event)
        elif self.screen_state == STATE_GUIDE:
            if event.key in {pygame.K_BACKSPACE, pygame.K_RETURN, pygame.K_ESCAPE}:
                self.screen_state = STATE_START
        elif self.screen_state == STATE_PLAYING:
            if self.is_lobby_waiting():
                if event.key == pygame.K_RETURN:
                    self.set_local_ready(True)
                elif event.key == pygame.K_BACKSPACE:
                    self.set_local_ready(False)
                return
            self.handle_play_key(event)

    def handle_join_key(self, event):
        if event.key == pygame.K_BACKSPACE:
            self.join_host_text = self.join_host_text[:-1]
        elif event.key == pygame.K_RETURN:
            self.start_join()
        else:
            ch = event.unicode
            if ch and (ch.isdigit() or ch in ".:"):
                self.join_host_text += ch

    def handle_play_key(self, event):
        if self.game_state and self.game_state.winner_pid is not None and event.key == pygame.K_r:
            self.return_to_menu()
            return

        if event.key == pygame.K_TAB:
            self.cycle_target(self.local_pids[0] if self.local_pids else 0)
            return

        move = None
        if event.key == pygame.K_w:
            move = (0, -1)
        elif event.key == pygame.K_s:
            move = (0, 1)
        elif event.key == pygame.K_a:
            move = (-1, 0)
        elif event.key == pygame.K_d:
            move = (1, 0)
        elif event.key == pygame.K_UP:
            move = (0, -1)
        elif event.key == pygame.K_DOWN:
            move = (0, 1)
        elif event.key == pygame.K_LEFT:
            move = (-1, 0)
        elif event.key == pygame.K_RIGHT:
            move = (1, 0)

        if move:
            pid = self.pid_for_movement_key(event.key)
            if pid is not None:
                self.send_or_apply(pid, {"action": "move", "dx": move[0], "dy": move[1]})
            return

        skill = self.skill_for_key(event.key)
        if skill:
            pid, slot = skill
            if pid in self.local_pids:
                self.select_or_cast_skill(pid, slot)
            return

        if event.key in {pygame.K_m, pygame.K_n}:
            pid = 0 if event.key == pygame.K_m else 1
            if pid in self.local_pids:
                self.send_or_apply(pid, {"action": "mark"})

    def handle_mouse_down(self, event):
        if event.button == 1:
            for button in self.buttons:
                if button.hit(event.pos):
                    self.activate_button(button.value)
                    return
            for name, slider in self.sliders.items():
                if slider.hit(event.pos):
                    self.active_slider = name
                    slider.update_from_mouse(event.pos)
                    self.apply_sliders_to_config()
                    return
            if self.screen_state == STATE_PLAYING:
                self.handle_game_left_click(event.pos)
        elif event.button == 3 and self.screen_state == STATE_PLAYING:
            if not self.is_network_mode():
                return
            cell = mouse_to_cell(self.last_viewports, event.pos)
            if cell:
                pid, x, y = cell
                if pid in self.local_pids:
                    self.send_or_apply(pid, {"action": "mark", "target": [x, y]})

    def handle_mouse_motion(self, event):
        if self.active_slider and self.active_slider in self.sliders:
            self.sliders[self.active_slider].update_from_mouse(event.pos)
            self.apply_sliders_to_config()

    def handle_game_left_click(self, pos):
        if not self.is_network_mode():
            return
        if not self.selected_skill:
            return
        cell = mouse_to_cell(self.last_viewports, pos)
        if not cell:
            self.selected_skill = None
            return
        click_pid, x, y = cell
        pid, slot = self.selected_skill
        state = self.game_state
        if not state or pid not in self.local_pids or not (0 <= pid < len(state.players)) or not (0 <= slot < len(state.players[pid].skills)):
            self.selected_skill = None
            return

        skill = SKILLS[state.players[pid].skills[slot]]
        target_pid = self.current_target_pid(pid)
        if skill.target_maze == "own":
            if click_pid != pid:
                state.players[pid].status_message = "Click your map"
                state.players[pid].status_timer = 2.0
                return
        elif skill.target_maze == "enemy":
            if click_pid != pid:
                target_pid = click_pid
                self.target_pids[pid] = click_pid

        self.send_or_apply(pid, {"action": "skill", "slot": slot, "target": [x, y], "target_pid": target_pid})
        self.selected_skill = None

    def update(self, dt: float):
        if self.screen_state != STATE_PLAYING:
            return
        if self.host_session:
            self.host_session.update(dt)
            self.game_state = self.host_session.state
        elif self.client_session:
            with self.client_session.lock:
                self.game_state = self.client_session.state
                if self.client_session.pid is not None:
                    self.local_pids = [self.client_session.pid]
        elif self.game_state:
            self.game_state.update(dt)
        if self.game_state and not self.is_lobby_waiting():
            self.handle_held_movement()

    def handle_held_movement(self):
        if not self.game_state or self.game_state.winner_pid is not None:
            return
        keys = pygame.key.get_pressed()
        for pid in list(self.local_pids):
            if not (0 <= pid < len(self.game_state.players)):
                continue
            player = self.game_state.players[pid]
            if player.move_timer > 0 or player.has_effect("stun"):
                continue
            move = self.held_move_for_pid(pid, keys)
            if move:
                self.send_or_apply(pid, {"action": "move", "dx": move[0], "dy": move[1]})

    def held_move_for_pid(self, pid: int, keys):
        if self.config.mode == MODE_LOCAL and pid == 0:
            key_order = [
                (pygame.K_w, (0, -1)),
                (pygame.K_s, (0, 1)),
                (pygame.K_a, (-1, 0)),
                (pygame.K_d, (1, 0)),
            ]
        elif self.config.mode == MODE_LOCAL and pid == 1:
            key_order = [
                (pygame.K_UP, (0, -1)),
                (pygame.K_DOWN, (0, 1)),
                (pygame.K_LEFT, (-1, 0)),
                (pygame.K_RIGHT, (1, 0)),
            ]
        else:
            key_order = [
                (pygame.K_w, (0, -1)),
                (pygame.K_s, (0, 1)),
                (pygame.K_a, (-1, 0)),
                (pygame.K_d, (1, 0)),
                (pygame.K_UP, (0, -1)),
                (pygame.K_DOWN, (0, 1)),
                (pygame.K_LEFT, (-1, 0)),
                (pygame.K_RIGHT, (1, 0)),
            ]
        for key, move in key_order:
            if keys[key]:
                return move
        return None

    def draw(self):
        set_language(self.config.language)
        self.buttons = []
        self.sliders = {}
        if self.screen_state == STATE_START:
            self.draw_start()
        elif self.screen_state == STATE_CONFIG:
            self.draw_config()
        elif self.screen_state == STATE_ROLES:
            self.draw_roles()
        elif self.screen_state == STATE_JOIN:
            self.draw_join()
        elif self.screen_state == STATE_GUIDE:
            self.draw_guide()
        elif self.screen_state == STATE_PLAYING:
            self.draw_playing()

    def draw_start(self):
        pygame.mouse.set_visible(True)
        draw_title(self.screen, self.t("start.subtitle"))
        draw_text(self.screen, self.t("language"), (50, 132), 18, COLORS["muted"], bold=True)
        lang_buttons = [("language.en", "en", "E"), ("language.zh", "zh", "C")]
        for i, (label_key, language, hotkey) in enumerate(lang_buttons):
            rect = pygame.Rect(50 + i * 132, 160, 118, 40)
            button = Button(rect, self.t(label_key), ("language", language), hotkey)
            button.draw(self.screen, selected=self.config.language == language)
            self.buttons.append(button)
        items = [
            (self.t("mode.local"), MODE_LOCAL, "1"),
            (self.t("mode.host"), MODE_HOST, "2"),
            (self.t("mode.join"), MODE_JOIN, "3"),
            (self.t("guide.title"), "guide", "H"),
            (self.t("quit"), "quit", "Q"),
        ]
        for i, (label, value, key) in enumerate(items):
            rect = pygame.Rect(SCREEN_W // 2 - 180, 176 + i * 62, 360, 50)
            button = Button(rect, label, value, key)
            button.draw(self.screen)
            self.buttons.append(button)
        draw_text(self.screen, self.t("start.note"), (SCREEN_W // 2, 540), 18, COLORS["muted"], center=True)

    def draw_guide(self):
        pygame.mouse.set_visible(True)
        draw_title(self.screen, self.t("guide.subtitle"))
        self.buttons.append(Button(pygame.Rect(50, 118, 120, 42), self.t("back"), "back"))
        self.buttons[-1].draw(self.screen)
        lang = self.config.language
        lines = guide_lines_zh() if lang == "zh" else guide_lines_en()
        x_left = 80
        x_right = SCREEN_W // 2 + 34
        y0 = 185
        for index, line in enumerate(lines):
            column = 0 if index < 14 else 1
            x = x_left if column == 0 else x_right
            y = y0 + (index % 14) * 34
            color = COLORS["gold"] if line.startswith("#") else COLORS["text"]
            text = line[1:] if line.startswith("#") else line
            draw_text(self.screen, text, (x, y), 18 if color == COLORS["gold"] else 16, color, bold=color == COLORS["gold"])
        draw_text(self.screen, self.t("guide.doc_note"), (SCREEN_W // 2, 690), 16, COLORS["muted"], center=True)

    def draw_config(self):
        pygame.mouse.set_visible(True)
        draw_title(self.screen, self.t("config.subtitle"))
        self.buttons.append(Button(pygame.Rect(50, 125, 120, 42), self.t("back"), "back"))
        self.buttons[-1].draw(self.screen)
        self.buttons.append(Button(pygame.Rect(SCREEN_W - 190, 125, 140, 42), self.t("continue"), "roles"))
        self.buttons[-1].draw(self.screen, selected=True)

        preset_x = 90
        for i, (name, size) in enumerate({"small": self.t("preset.small"), "medium": self.t("preset.medium"), "large": self.t("preset.large")}.items()):
            b = Button(pygame.Rect(preset_x + i * 150, 200, 125, 42), size, ("preset", name), str(i + 1))
            b.draw(self.screen, selected=self.config.maze_size_preset == name)
            self.buttons.append(b)

        self.sliders["width"] = Slider(pygame.Rect(90, 285, 460, 24), self.t("slider.width"), 21, 61, self.config.maze_width, 2)
        self.sliders["height"] = Slider(pygame.Rect(90, 345, 460, 24), self.t("slider.height"), 15, 41, self.config.maze_height, 2)
        self.sliders["loop"] = Slider(pygame.Rect(90, 405, 460, 24), self.t("slider.loop"), 0, 0.25, self.config.loop_ratio, 0.01)
        self.sliders["overlap"] = Slider(pygame.Rect(90, 465, 460, 24), self.t("slider.overlap"), 0, 1, self.config.overlap_rate, 0.1)
        self.sliders["trap"] = Slider(pygame.Rect(90, 590, 220, 24), self.t("slider.trap"), 0, 3, self.config.trap_level, 1)
        self.sliders["pushable"] = Slider(pygame.Rect(380, 590, 220, 24), self.t("slider.pushable"), 0, 3, self.config.pushable_level, 1)
        self.sliders["danger"] = Slider(pygame.Rect(670, 590, 220, 24), self.t("slider.danger"), 0, 3, self.config.danger_level, 1)
        for slider in self.sliders.values():
            slider.draw(self.screen)

        fog_buttons = [(FOG_HEAVY, self.t("fog.heavy")), (FOG_LIGHT, self.t("fog.light")), (FOG_NONE, self.t("fog.none"))]
        for i, (fog, label) in enumerate(fog_buttons):
            b = Button(pygame.Rect(650, 220 + i * 62, 190, 44), label, ("fog", fog))
            b.draw(self.screen, selected=self.config.fog_level == fog)
            self.buttons.append(b)

        count_buttons = [(2, self.t("players.n", count=2)), (3, self.t("players.n", count=3)), (4, self.t("players.n", count=4))]
        for i, (count, label) in enumerate(count_buttons):
            b = Button(pygame.Rect(930, 220 + i * 62, 170, 44), label, ("players", count))
            b.enabled = self.config.mode != MODE_LOCAL or count == 2
            b.draw(self.screen, selected=self.config.player_count == count)
            self.buttons.append(b)

        toggle_items = [
            (self.t("toggle.collision"), "collision", self.config.collision_enabled),
            (self.t("toggle.trail"), "trail", self.config.trail_enabled),
        ]
        for i, (label, value, enabled) in enumerate(toggle_items):
            b = Button(pygame.Rect(650, 425 + i * 58, 190, 44), label, ("toggle", value))
            b.draw(self.screen, selected=enabled)
            self.buttons.append(b)

        draw_config_summary(self.screen, self.config, 900, 395)
        draw_text(self.screen, self.t("config.note"), (90, 665), 17, COLORS["muted"])

    def draw_roles(self):
        pygame.mouse.set_visible(True)
        draw_title(self.screen, self.t("roles.subtitle"))
        self.buttons.append(Button(pygame.Rect(50, 118, 120, 42), self.t("back"), "config"))
        self.buttons[-1].draw(self.screen)
        self.buttons.append(Button(pygame.Rect(SCREEN_W - 190, 118, 140, 42), self.t("start"), "start_game"))
        self.buttons[-1].draw(self.screen, selected=True)

        selectable_count = 1 if self.config.mode == MODE_HOST else self.config.player_count
        for pid in range(selectable_count):
            b = Button(pygame.Rect(260 + pid * 120, 130, 96, 38), f"P{pid + 1}", ("select_pid", pid), str(pid + 1))
            b.draw(self.screen, selected=self.role_select_pid == pid)
            self.buttons.append(b)

        role_ids = list(ROLES)
        for i, role_id in enumerate(role_ids):
            row = i // 3
            col = i % 3
            rect = pygame.Rect(95 + col * 370, 205 + row * 230, 330, 200)
            selected = self.roles[self.role_select_pid] == role_id
            draw_role_card(self.screen, rect, role_id, selected)
            self.buttons.append(Button(rect, "", ("role", role_id)))

        draw_text(self.screen, self.t("roles.tip"), (SCREEN_W // 2, 690), 17, COLORS["muted"], center=True)

    def draw_join(self):
        pygame.mouse.set_visible(True)
        draw_title(self.screen, self.t("join.subtitle"))
        self.buttons.append(Button(pygame.Rect(50, 125, 120, 42), self.t("back"), "back"))
        self.buttons[-1].draw(self.screen)
        self.buttons.append(Button(pygame.Rect(SCREEN_W // 2 - 90, 390, 180, 50), self.t("join.connect"), "connect"))
        self.buttons[-1].draw(self.screen, selected=True)
        draw_text(self.screen, self.t("join.host_ip"), (SCREEN_W // 2 - 180, 260), 20, COLORS["muted"])
        input_rect = pygame.Rect(SCREEN_W // 2 - 180, 295, 360, 48)
        pygame.draw.rect(self.screen, (32, 37, 48), input_rect, border_radius=8)
        pygame.draw.rect(self.screen, COLORS["accent"], input_rect, 2, border_radius=8)
        draw_text(self.screen, self.join_host_text, (input_rect.x + 12, input_rect.y + 12), 22, COLORS["text"])
        if self.client_session and self.client_session.error:
            draw_text(self.screen, self.client_session.error, (SCREEN_W // 2, 470), 18, COLORS["bad"], center=True)
        role_ids = list(ROLES)
        for i, role_id in enumerate(role_ids):
            rect = pygame.Rect(115 + i * 210, 520, 190, 90)
            role = ROLES[role_id]
            b = Button(rect, "", ("join_role", role_id))
            pygame.draw.rect(self.screen, (32, 37, 48), rect, border_radius=8)
            pygame.draw.rect(self.screen, COLORS["accent"] if self.join_role == role_id else COLORS["line"], rect, 2, border_radius=8)
            draw_text(self.screen, role_name(role_id, role.name, self.config.language), (rect.centerx, rect.y + 16), 18, COLORS["text"], center=True, bold=True)
            draw_text(self.screen, role_summary(role_id, role.summary, self.config.language)[:22], (rect.centerx, rect.y + 48), 13, COLORS["muted"], center=True)
            self.buttons.append(b)

    def draw_playing(self):
        if self.is_lobby_waiting():
            pygame.mouse.set_visible(True)
            self.draw_network_lobby()
            return
        network_mouse = self.is_network_mode()
        pygame.mouse.set_visible(network_mouse)
        if not self.game_state:
            draw_title(self.screen, self.t("playing.waiting_state"))
            return
        mouse_cell = None
        if network_mouse:
            cell = mouse_to_cell(self.last_viewports, pygame.mouse.get_pos())
            if cell:
                _pid, x, y = cell
                mouse_cell = (x, y)
        self.last_viewports = draw_game(self.screen, self.game_state, self.local_pids, self.selected_skill, mouse_cell, self.target_pids, self.config.language)
        if self.client_session and self.client_session.error:
            draw_text(self.screen, self.client_session.error, (SCREEN_W // 2, 28), 18, COLORS["bad"], center=True)

    def activate_button(self, value):
        if value == "quit":
            self.running = False
        elif value == "back":
            self.screen_state = STATE_START
        elif value == "config":
            self.screen_state = STATE_CONFIG
        elif value == "roles":
            self.screen_state = STATE_ROLES
        elif value == "start_game":
            self.start_game_from_config()
        elif value == "connect":
            self.start_join()
        elif value in {MODE_LOCAL, MODE_HOST}:
            self.open_config(value)
        elif value == MODE_JOIN:
            self.screen_state = STATE_JOIN
        elif value == "guide":
            self.screen_state = STATE_GUIDE
        elif isinstance(value, tuple):
            kind = value[0]
            if kind == "language":
                self.set_language(value[1])
            elif kind == "preset":
                self.config.maze_size_preset = value[1]
                if value[1] == "small":
                    self.config.maze_width, self.config.maze_height = 21, 15
                elif value[1] == "medium":
                    self.config.maze_width, self.config.maze_height = 31, 21
                else:
                    self.config.maze_width, self.config.maze_height = 41, 31
            elif kind == "fog":
                self.config.fog_level = value[1]
            elif kind == "players":
                if self.config.mode == MODE_LOCAL and value[1] != 2:
                    return
                self.config.player_count = value[1]
                while len(self.roles) < self.config.player_count:
                    self.roles.append("explorer")
                self.role_select_pid = min(self.role_select_pid, self.config.player_count - 1)
            elif kind == "toggle":
                if value[1] == "collision":
                    self.config.collision_enabled = not self.config.collision_enabled
                elif value[1] == "trail":
                    self.config.trail_enabled = not self.config.trail_enabled
            elif kind == "select_pid":
                if self.config.mode == MODE_HOST and value[1] != 0:
                    return
                self.role_select_pid = value[1]
            elif kind == "role":
                self.roles[self.role_select_pid] = value[1]
            elif kind == "join_role":
                self.join_role = value[1]

    def open_config(self, mode):
        self.config.mode = mode
        if mode == MODE_LOCAL:
            self.config.player_count = 2
            self.role_select_pid = min(self.role_select_pid, 1)
        elif mode == MODE_HOST:
            self.role_select_pid = 0
        self.screen_state = STATE_CONFIG

    def apply_sliders_to_config(self):
        self.config.maze_width = int(self.sliders["width"].value)
        self.config.maze_height = int(self.sliders["height"].value)
        self.config.loop_ratio = float(self.sliders["loop"].value)
        self.config.overlap_rate = float(self.sliders["overlap"].value)
        self.config.trap_level = int(self.sliders["trap"].value)
        self.config.pushable_level = int(self.sliders["pushable"].value)
        self.config.danger_level = int(self.sliders["danger"].value)
        self.config.maze_size_preset = "custom"
        self.config.normalize()

    def start_game_from_config(self):
        if self.config.mode == MODE_LOCAL:
            self.config.player_count = 2
        self.config.normalize()
        roles = self.roles[: self.config.player_count]
        self.selected_skill = None
        self.last_viewports = {}
        if self.config.mode == MODE_HOST:
            self.host_session = HostSession(self.config, roles)
            self.host_session.start()
            self.client_session = None
            self.game_state = None
            self.local_pids = [0]
        else:
            self.host_session = None
            self.client_session = None
            self.game_state = GameState(self.config, roles)
            self.local_pids = list(range(min(2, self.config.player_count)))
        self.screen_state = STATE_PLAYING

    def start_join(self):
        self.config.mode = MODE_JOIN
        self.client_session = ClientSession(self.join_host_text or "127.0.0.1", self.config.port, self.join_role)
        if self.client_session.connect():
            self.host_session = None
            self.game_state = None
            self.local_pids = [0]
            self.screen_state = STATE_PLAYING

    def return_to_menu(self):
        if self.host_session:
            self.host_session.stop()
        if self.client_session:
            self.client_session.disconnect()
        self.host_session = None
        self.client_session = None
        self.game_state = None
        self.selected_skill = None
        self.screen_state = STATE_START

    def pid_for_movement_key(self, key):
        if self.config.mode == MODE_LOCAL:
            if key in {pygame.K_w, pygame.K_a, pygame.K_s, pygame.K_d}:
                return 0 if 0 in self.local_pids else None
            if key in {pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT}:
                return 1 if 1 in self.local_pids else None
        if self.local_pids:
            return self.local_pids[0]
        return None

    def skill_for_key(self, key):
        p1 = {
            pygame.K_1: 0,
            pygame.K_2: 1,
            pygame.K_3: 2,
            pygame.K_4: 3,
            pygame.K_5: 4,
            pygame.K_6: 5,
            pygame.K_7: 6,
            pygame.K_8: 7,
        }
        p2 = {
            pygame.K_COMMA: 0,
            pygame.K_PERIOD: 1,
            pygame.K_SLASH: 2,
            pygame.K_SEMICOLON: 3,
            pygame.K_LEFTBRACKET: 4,
            pygame.K_RIGHTBRACKET: 5,
            pygame.K_MINUS: 6,
            pygame.K_EQUALS: 7,
        }
        if self.config.mode == MODE_LOCAL:
            if key in p1:
                return 0, p1[key]
            if key in p2:
                return 1, p2[key]
        elif self.local_pids:
            pid = self.local_pids[0]
            if key in p1:
                return pid, p1[key]
            if key in p2:
                return pid, p2[key]
        return None

    def select_or_cast_skill(self, pid: int, slot: int):
        state = self.game_state
        if not state or pid >= len(state.players) or slot >= len(state.players[pid].skills):
            return
        skill_id = state.players[pid].skills[slot]
        skill = SKILLS[skill_id]
        if self.is_network_mode() and skill.needs_mouse:
            self.selected_skill = (pid, slot)
            state.players[pid].status_message = "Select target cell"
            state.players[pid].status_timer = 3.0
            return
        self.selected_skill = None
        self.send_or_apply(pid, {"action": "skill", "slot": slot, "target_pid": self.current_target_pid(pid)})

    def send_or_apply(self, pid: int, payload):
        if self.host_session and pid == 0:
            self.host_session.local_input(payload)
        elif self.client_session:
            self.client_session.send_input(payload)
        elif self.game_state:
            apply_input(self.game_state, pid, payload)

    def is_lobby_waiting(self):
        if self.host_session and not self.host_session.lobby.game_started:
            return True
        if self.client_session:
            with self.client_session.lock:
                lobby = self.client_session.lobby
                state = self.client_session.state
            return bool(lobby and not lobby.get("game_started") and state is None)
        return False

    def draw_network_lobby(self):
        draw_title(self.screen, self.t("lobby.subtitle"))
        lobby = None
        my_pid = 0
        if self.host_session:
            lobby = self.host_session.lobby.as_dict()
            my_pid = 0
        elif self.client_session:
            with self.client_session.lock:
                lobby = self.client_session.lobby
                my_pid = self.client_session.pid if self.client_session.pid is not None else 0
        if not lobby:
            draw_text(self.screen, self.t("lobby.connecting"), (SCREEN_W // 2, 260), 28, COLORS["gold"], center=True)
            return
        draw_text(self.screen, self.t("lobby.you_are", pid=my_pid + 1), (SCREEN_W // 2, 150), 24, COLORS["gold"], center=True, bold=True)
        roles = lobby.get("roles", [])
        ready = {int(k): v for k, v in lobby.get("ready", {}).items()}
        connected = {int(k): v for k, v in lobby.get("connected", {}).items()}
        for pid in range(lobby.get("player_count", 2)):
            rect = pygame.Rect(210 + pid * 220, 220, 180, 150)
            pygame.draw.rect(self.screen, (32, 37, 48), rect, border_radius=8)
            pygame.draw.rect(self.screen, COLORS["accent"] if pid == my_pid else COLORS["line"], rect, 2, border_radius=8)
            draw_text(self.screen, f"P{pid + 1}", (rect.centerx, rect.y + 18), 24, COLORS["text"], center=True, bold=True)
            role_id = roles[pid] if pid < len(roles) else "explorer"
            role = ROLES.get(role_id, ROLES["explorer"])
            draw_text(self.screen, role_name(role_id, role.name, self.config.language), (rect.centerx, rect.y + 58), 18, COLORS["gold"], center=True)
            status = self.t("lobby.ready") if ready.get(pid) else self.t("lobby.not_ready")
            if not connected.get(pid):
                status = self.t("lobby.waiting")
            draw_text(self.screen, status, (rect.centerx, rect.y + 96), 18, COLORS["good"] if ready.get(pid) else COLORS["muted"], center=True)
        draw_text(self.screen, self.t("lobby.note"), (SCREEN_W // 2, 450), 18, COLORS["muted"], center=True)

    def set_local_ready(self, ready: bool):
        if self.host_session:
            self.host_session.local_input({"action": "ready", "ready": ready})
        elif self.client_session:
            self.client_session.send_ready(ready)

    def current_target_pid(self, pid: int):
        state = self.game_state
        if not state or len(state.players) <= 1:
            return None
        current = self.target_pids.get(pid)
        if current is not None and 0 <= current < len(state.players) and current != pid:
            return current
        for player in state.players:
            if player.pid != pid:
                self.target_pids[pid] = player.pid
                return player.pid
        return None

    def cycle_target(self, pid: int):
        state = self.game_state
        if not state or len(state.players) <= 1:
            return
        candidates = [p.pid for p in state.players if p.pid != pid]
        current = self.current_target_pid(pid)
        if current not in candidates:
            self.target_pids[pid] = candidates[0]
            return
        idx = candidates.index(current)
        self.target_pids[pid] = candidates[(idx + 1) % len(candidates)]


def guide_lines_zh() -> list[str]:
    return [
        "#基础流程",
        "启动页：1 同屏，2 建房，3 加入，H 查看本页。",
        "配置页：选择地图大小、环路复杂度、雾、人数和地图特色。",
        "角色页：同屏可给 P1/P2 选角色；建房端只选 P1。",
        "胜利：收集指定果实后终点解锁，走到终点获胜。",
        "#移动和目标",
        "同屏 P1：WASD 移动；P2：方向键移动。",
        "联网：本机玩家可用 WASD 或方向键移动。",
        "Tab：切换当前锁定对手，debuff/对方地图技能作用于该目标。",
        "M/N：同屏给 P1/P2 当前格做标记；联网右键标记可见格。",
        "#技能键",
        "P1 技能：1 2 3 4 5 6 7 8。",
        "P2 技能：, . / ; [ ] - =。",
        "技能格显示 CD 表示基础冷却；x1/xN 表示一次性奖励次数。",
        "#同屏释放",
        "同屏开局后鼠标隐藏且不用于释放技能。",
        "格子技能默认向角色面前或锁定对手面前的合法格释放。",
        "造墙、破墙、陷阱不再受距离限制，但仍要目标格合法。",
        "假果自动随机生成在锁定对手地图，不需要选位置。",
        "#联网释放",
        "联网保留鼠标：点击格子技能后，再点主地图坐标释放。",
        "选中技能后屏幕会提示当前目标和释放方式。",
        "对手地图技能会作用到锁定对手的同坐标格。",
        "需要对手目标的技能先用 Tab 选 P2/P3/P4。",
        "建房/加入大厅中 Enter 准备，Backspace 取消准备。",
        "#任务",
        "必做任务默认只有收集果实。",
        "奖励任务会随机出现，完成后给一次性或可配置奖励技能。",
        "闭合环路任务要求走回旧格形成圈，不同环路会去重。",
    ]


def guide_lines_en() -> list[str]:
    return [
        "#Flow",
        "Start: 1 Local, 2 Host, 3 Join, H Guide.",
        "Config: choose size, loop ratio, fog, players, and features.",
        "Roles: local selects P1/P2; host selects P1 only.",
        "Win: collect required fruit, unlock goal, then reach it.",
        "#Move and Target",
        "Local P1: WASD. Local P2: arrow keys.",
        "Network: local player can use WASD or arrows.",
        "Tab switches current target for enemy skills and debuffs.",
        "M/N mark local P1/P2 cells; right click marks visible network cells.",
        "#Skill Keys",
        "P1 skills: 1 2 3 4 5 6 7 8.",
        "P2 skills: , . / ; [ ] - =.",
        "CD shows base cooldown; x1/xN shows one-shot reward uses.",
        "#Local Cast",
        "Local play hides the mouse after game start.",
        "Cell skills cast toward the player or locked target by default.",
        "Build, Break, and Trap ignore distance but still need legal cells.",
        "Fake Fruit auto-spawns on the locked enemy map.",
        "#Network Cast",
        "Network keeps mouse targeting for cell skills.",
        "Select a cell skill, then click a main-map coordinate.",
        "Enemy-map skills affect that coordinate on the locked target.",
        "Use Tab before enemy skills to choose P2/P3/P4.",
        "In lobby: Enter ready, Backspace unready.",
        "#Tasks",
        "Required task is fruit collection by default.",
        "Bonus tasks appear randomly and grant one-shot/configurable skills.",
        "Loop tasks count closed paths and de-duplicate same loops.",
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", action="store_true", help="Start directly as host")
    parser.add_argument("--join", default="", help="Start directly as client and join host IP")
    args = parser.parse_args()
    app = MazeBattleApp()
    if args.host:
        app.open_config(MODE_HOST)
    elif args.join:
        app.join_host_text = args.join
        app.screen_state = STATE_JOIN
    app.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
