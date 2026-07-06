import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from engine import FAKE_FRUIT, FLOOR, PUSHABLE_WALL, GameConfig, GameState, SKILLS, TRAP, WALL
from main import (
    MazeBattleApp,
    MODE_JOIN,
    MODE_HOST,
    MODE_LOCAL,
    STATE_CONFIG,
    STATE_GUIDE,
    STATE_JOIN,
    STATE_PLAYING,
    STATE_ROLES,
    STATE_START,
)


def close_app_without_quitting_pygame(app):
    if app.host_session:
        app.host_session.stop()
    if app.client_session:
        app.client_session.disconnect()


def check_all_skills_keyboard_cast():
    state = GameState(GameConfig(player_count=2), ["explorer", "saboteur"])
    player = state.players[0]
    player.skills = list(SKILLS)
    failures = []
    for index, skill_id in enumerate(player.skills):
        player.cooldowns.clear()
        _ok, message = state.cast_skill(0, index, target_pid=1)
        if message == "Select target cell":
            failures.append(skill_id)
    return failures


def check_network_mouse_targeting():
    app = MazeBattleApp()
    app.open_config(MODE_HOST)
    app.game_state = GameState(app.config, ["explorer", "saboteur"])
    app.local_pids = [0]
    app.select_or_cast_skill(0, 0)
    result = app.selected_skill == (0, 0)
    close_app_without_quitting_pygame(app)
    return result


def check_local_forces_two_players():
    app = MazeBattleApp()
    app.config.player_count = 4
    app.open_config(MODE_LOCAL)
    app.start_game_from_config()
    result = (app.config.player_count, len(app.game_state.players), app.local_pids)
    close_app_without_quitting_pygame(app)
    return result


def check_button_overlaps():
    app = MazeBattleApp()
    report = []
    for page in [STATE_START, STATE_CONFIG, STATE_ROLES, STATE_JOIN, STATE_GUIDE]:
        if page == STATE_CONFIG:
            app.open_config(MODE_LOCAL)
        else:
            app.screen_state = page
        app.draw()
        rects = [
            (index, button.rect, button.label, button.value)
            for index, button in enumerate(app.buttons)
            if button.rect.width > 0 and button.rect.height > 0
        ]
        overlaps = []
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                if rects[i][1].colliderect(rects[j][1]):
                    overlaps.append((rects[i][2], rects[i][3], rects[j][2], rects[j][3]))
        report.append((page, len(rects), overlaps))
    close_app_without_quitting_pygame(app)
    return report


class FakeKeys:
    def __init__(self, pressed):
        self.pressed = set(pressed)

    def __getitem__(self, key):
        return key in self.pressed


def check_local_held_key_separation():
    import pygame
    app = MazeBattleApp()
    app.open_config(MODE_LOCAL)
    p1_arrow = app.held_move_for_pid(0, FakeKeys([pygame.K_RIGHT]))
    p1_wasd = app.held_move_for_pid(0, FakeKeys([pygame.K_d]))
    p2_arrow = app.held_move_for_pid(1, FakeKeys([pygame.K_RIGHT]))
    p2_wasd = app.held_move_for_pid(1, FakeKeys([pygame.K_d]))
    close_app_without_quitting_pygame(app)
    return p1_arrow is None and p1_wasd == (1, 0) and p2_arrow == (1, 0) and p2_wasd is None


def check_reward_slot_cooldown_independent():
    state = GameState(GameConfig(player_count=2), ["explorer", "explorer"])
    player = state.players[0]
    player.skills = ["shield", "shield"]
    player.skill_uses = [None, 1]
    player.skill_cooldowns = [0.0, 0.0]
    ok, _message = state.cast_skill(0, 1, target_pid=1)
    return ok and player.skills == ["shield"] and player.skill_uses == [None] and player.cooldown_for_slot(0) == 0


def check_default_required_tasks():
    state = GameState(GameConfig(player_count=2), ["explorer", "saboteur"])
    required = {task_id for task_id, task in state.players[0].tasks.items() if task.required_for_win}
    return required


def check_random_bonus_task_slots():
    state = GameState(GameConfig(player_count=2, bonus_task_slots=3), ["explorer", "saboteur"])
    player = state.players[0]
    bonus = [task for task in player.tasks.values() if not task.required_for_win]
    return len(player.tasks), len(bonus), set(player.tasks).issubset({"fruit", "shape", "loop_length", "unique_loops", "opponent_trap", "meet"})


def check_goal_unlock_by_fruit():
    state = GameState(GameConfig(player_count=2, fruit_required=1), ["explorer", "saboteur"])
    player = state.players[0]
    locked_before = not state.goal_unlocked(0) and player.known_own_endpoint is None
    player.fruits = 1
    state.update_tasks(0)
    unlocked_after = state.goal_unlocked(0) and player.known_own_endpoint == player.endpoint
    return locked_before and unlocked_after


def check_loop_tasks_progress():
    state = GameState(GameConfig(player_count=2, random_bonus_tasks_enabled=False), ["explorer", "saboteur"])
    player = state.players[0]
    player.trail = [(1, 1), (2, 1), (2, 2), (1, 2), (1, 1), (3, 1), (3, 2), (1, 2), (1, 1)]
    player.longest_loop_length = 0
    player.unique_loop_keys.clear()
    from engine import update_loop_stats
    update_loop_stats(player)
    state.update_tasks(0)
    return player.longest_loop_length >= 4 and len(player.unique_loop_keys) >= 1


def check_path_recalculation_on_map_edit():
    state = GameState(GameConfig(player_count=2), ["explorer", "saboteur"])
    player = state.players[0]
    before = list(player.path_to_goal)
    target = next((pos for pos in before[1:-1] if state.mazes[0].get(*pos) == FLOOR), None)
    if target is None:
        return False
    state.apply_map_edit(0, target, WALL, None, 1)
    return bool(player.path_to_goal) and player.path_to_goal != before


def first_cell(state, maze_pid, cells):
    maze = state.mazes[maze_pid]
    for y in range(1, maze.height - 1):
        for x in range(1, maze.width - 1):
            if maze.get(x, y) in cells and not state.cell_has_player(maze_pid, (x, y)):
                return (x, y)
    return None


def nearby_floor_cell(state, maze_pid, origin, max_dist):
    maze = state.mazes[maze_pid]
    best = None
    best_dist = 10**9
    for y in range(1, maze.height - 1):
        for x in range(1, maze.width - 1):
            cell = (x, y)
            if cell == origin:
                continue
            if maze.get(x, y) != FLOOR or state.cell_has_player(maze_pid, cell):
                continue
            dist = abs(x - origin[0]) + abs(y - origin[1])
            if dist <= max_dist and dist < best_dist:
                best = cell
                best_dist = dist
    return best


def legal_skill_target(state, pid, skill_id):
    target_pid = 1 if pid == 0 else 0
    if skill_id in {"break_wall", "perm_break"}:
        return first_cell(state, pid, {WALL, PUSHABLE_WALL}), pid
    if skill_id in {"build_wall", "perm_build", "trap_area"}:
        return first_cell(state, target_pid, {FLOOR}), target_pid
    if skill_id == "move_enemy_goal":
        return state.players[target_pid].endpoint, target_pid
    if skill_id == "teleport":
        return nearby_floor_cell(state, pid, state.players[pid].position, SKILLS[skill_id].cast_range), pid
    if skill_id == "reveal_own_area":
        return state.players[pid].position, pid
    if skill_id == "reveal_enemy_area":
        return state.players[target_pid].position, target_pid
    return None, target_pid


def check_all_skills_with_legal_targets():
    failures = []
    for skill_id in SKILLS:
        state = GameState(GameConfig(player_count=2, fruit_required=1), ["explorer", "saboteur"])
        player = state.players[0]
        player.skills = [skill_id]
        player.skill_uses = [None]
        player.skill_cooldowns = [0.0]
        player.fruits = 1
        state.update_tasks(0)
        if SKILLS[skill_id].target_type in {"enemy", "enemy_player"}:
            state.players[1].position = player.position
        target, target_pid = legal_skill_target(state, 0, skill_id)
        ok, message = state.cast_skill(0, 0, target, target_pid)
        if not ok:
            failures.append((skill_id, message))
    return failures


def check_unlimited_map_edit_and_fake_auto():
    state = GameState(GameConfig(player_count=2), ["breaker", "saboteur"])
    player = state.players[0]
    enemy = state.players[1]
    far_wall = first_cell(state, 0, {WALL, PUSHABLE_WALL})
    far_floor = first_cell(state, 1, {FLOOR})
    player.skills = ["break_wall", "build_wall", "trap_area", "fake_fruit"]
    player.skill_uses = [None, None, None, None]
    player.skill_cooldowns = [0.0, 0.0, 0.0, 0.0]
    results = []
    results.append(state.cast_skill(0, 0, far_wall, 1)[0])
    player.skill_cooldowns[1] = 0
    results.append(state.cast_skill(0, 1, far_floor, 1)[0])
    trap_floor = first_cell(state, 1, {FLOOR})
    player.skill_cooldowns[2] = 0
    results.append(state.cast_skill(0, 2, trap_floor, 1)[0])
    player.skill_cooldowns[3] = 0
    before_fake = sum(row.count(FAKE_FRUIT) for row in state.mazes[1].grid)
    results.append(state.cast_skill(0, 3, None, 1)[0])
    after_fake = sum(row.count(FAKE_FRUIT) for row in state.mazes[1].grid)
    return all(results) and after_fake == before_fake + 1 and enemy.status_message == "Fake fruit appeared"


def check_network_enemy_coordinate_targeting():
    app = MazeBattleApp()
    app.config.mode = MODE_HOST
    app.config.player_count = 3
    app.config.normalize()
    app.game_state = GameState(app.config, ["explorer", "saboteur", "trapper"])
    app.local_pids = [0]
    app.screen_state = STATE_PLAYING
    app.target_pids[0] = 2
    player = app.game_state.players[0]
    player.skills = ["build_wall"]
    player.skill_uses = [None]
    player.skill_cooldowns = [0.0]
    target = first_cell(app.game_state, 2, {FLOOR})
    if target is None:
        close_app_without_quitting_pygame(app)
        return False
    before_p2 = app.game_state.mazes[1].get(target[0], target[1])
    app.selected_skill = (0, 0)
    app.draw()
    viewport = app.last_viewports[0]
    ox, oy = viewport["origin"]
    tile = viewport["tile"]
    click = (ox + target[0] * tile + tile // 2, oy + target[1] * tile + tile // 2)
    app.handle_game_left_click(click)
    result = app.game_state.mazes[2].get(target[0], target[1]) == WALL and app.game_state.mazes[1].get(target[0], target[1]) == before_p2
    close_app_without_quitting_pygame(app)
    return result


if __name__ == "__main__":
    print("local_default_target_failures", check_all_skills_keyboard_cast())
    print("network_mouse_targeting", check_network_mouse_targeting())
    print("local_forces_two", check_local_forces_two_players())
    print("button_overlaps", check_button_overlaps())
    print("local_held_key_separation", check_local_held_key_separation())
    print("reward_slot_cooldown_independent", check_reward_slot_cooldown_independent())
    print("default_required_tasks", check_default_required_tasks())
    print("random_bonus_task_slots", check_random_bonus_task_slots())
    print("goal_unlock_by_fruit", check_goal_unlock_by_fruit())
    print("loop_tasks_progress", check_loop_tasks_progress())
    print("path_recalculation_on_map_edit", check_path_recalculation_on_map_edit())
    print("all_skills_with_legal_targets", check_all_skills_with_legal_targets())
    print("unlimited_map_edit_and_fake_auto", check_unlimited_map_edit_and_fake_auto())
    print("network_enemy_coordinate_targeting", check_network_enemy_coordinate_targeting())
    import pygame
    pygame.quit()
