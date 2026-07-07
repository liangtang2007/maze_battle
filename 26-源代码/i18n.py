from __future__ import annotations

import re


SUPPORTED_LANGUAGES = {"en", "zh"}


TEXT: dict[str, dict[str, str]] = {
    "en": {
        "start.subtitle": "Mouse and keyboard menu. Choose a mode to begin.",
        "start.note": "This remake keeps the old prototype as resources and rebuilds the game flow.",
        "language": "Language",
        "language.en": "English",
        "language.zh": "Chinese",
        "mode.local": "Local Same Screen",
        "mode.host": "Host Network Room",
        "mode.join": "Join Network Room",
        "guide.title": "Player Guide",
        "guide.subtitle": "Player guide and controls",
        "guide.doc_note": "Full guide: docs/玩家操作指南.md",
        "quit": "Quit",
        "config.subtitle": "Map, fog, and mode configuration",
        "back": "Back",
        "continue": "Continue",
        "start": "Start",
        "preset.small": "Small",
        "preset.medium": "Medium",
        "preset.large": "Large",
        "slider.width": "Width",
        "slider.height": "Height",
        "slider.loop": "Loop Ratio",
        "slider.overlap": "Overlap",
        "slider.trap": "Trap Level",
        "slider.pushable": "Pushable Level",
        "slider.danger": "Danger Level",
        "fog.heavy": "Heavy Fog",
        "fog.light": "Light Fog",
        "fog.none": "No Fog",
        "players.n": "{count} Players",
        "toggle.collision": "Collision",
        "toggle.trail": "Trail",
        "config.note": "Loop Ratio controls route complexity. Trap, pushable and danger levels are independent map features.",
        "summary.size": "Size",
        "summary.loop": "Loop Ratio",
        "summary.overlap": "Overlap",
        "summary.fog": "Fog",
        "summary.players": "Players",
        "summary.features": "Features",
        "roles.subtitle": "Character selection. Skills can be rebalanced later.",
        "roles.tip": "Tip: roles are temporary presets. The final version can bind skills after balance testing.",
        "join.subtitle": "Join network room",
        "join.host_ip": "Host IP",
        "join.connect": "Connect",
        "playing.waiting_state": "Waiting for state...",
        "lobby.subtitle": "Network lobby. Enter = ready, Backspace = unready.",
        "lobby.connecting": "Connecting...",
        "lobby.you_are": "You are P{pid}",
        "lobby.ready": "Ready",
        "lobby.not_ready": "Not Ready",
        "lobby.waiting": "Waiting",
        "lobby.note": "Host starts automatically when every configured player is connected and ready.",
        "hud.enemy_intel": "Enemy Intel",
        "hud.no_scan": "No scan",
        "hud.progress_board": "Progress Board",
        "hud.tasks": "tasks",
        "hud.target": "Target",
        "hud.fruit": "Fruit",
        "hud.goal": "Goal",
        "hud.unknown": "Unknown",
        "hud.locked": "Locked",
        "hud.enemy_goal": "Enemy Goal",
        "hud.effects": "Effects",
        "hud.tasks_panel": "Tasks",
        "hud.required_short": "WIN",
        "hud.bonus_short": "BONUS",
        "hud.skills": "Skills",
        "hud.start_in": "START IN",
        "hud.done": "DONE",
        "hud.foes": "foes",
        "result.wins": "{name} WINS!",
        "result.prompt": "Press R to return to menu, ESC to quit",
        "role.explorer.name": "Explorer",
        "role.explorer.summary": "Vision and route control.",
        "role.saboteur.name": "Saboteur",
        "role.saboteur.summary": "Enemy disruption and fake rewards.",
        "role.breaker.name": "Breaker",
        "role.breaker.summary": "Mobility and wall control.",
        "role.trapper.name": "Trapper",
        "role.trapper.summary": "Zones, traps, and stealing.",
        "role.analyst.name": "Analyst",
        "role.analyst.summary": "Enemy intel and stealth.",
        "skill.reveal_own_area.name": "Own Scan",
        "skill.reveal_enemy_area.name": "Enemy Scan",
        "skill.reveal_enemy_pos.name": "Tracker",
        "skill.hide_self.name": "Hide",
        "skill.reveal_own_goal.name": "Own Goal",
        "skill.reveal_enemy_goal.name": "Enemy Goal",
        "skill.break_wall.name": "Break",
        "skill.perm_break.name": "Perm Break",
        "skill.build_wall.name": "Build",
        "skill.perm_build.name": "Perm Build",
        "skill.move_enemy_goal.name": "Move Goal",
        "skill.blind_enemy.name": "Blind",
        "skill.fake_fruit.name": "Fake",
        "skill.speed_up.name": "Haste",
        "skill.slow_enemy.name": "Slow",
        "skill.confuse_enemy.name": "Reverse",
        "skill.trap_area.name": "Trap",
        "skill.stun_enemy.name": "Bind",
        "skill.shield.name": "Shield",
        "skill.teleport.name": "Blink",
        "skill.steal.name": "Steal",
        "task.fruit.name": "Collect Fruits",
        "task.shape.name": "Make 4 Turns",
        "task.loop_length.name": "Close Loop",
        "task.unique_loops.name": "Unique Loops",
        "task.opponent_trap.name": "Trap Opponents",
        "task.meet.name": "Meet Opponents",
        "effect.hidden.name": "Hidden",
        "effect.blind.name": "Blind",
        "effect.haste.name": "Haste",
        "effect.slow.name": "Slow",
        "effect.confuse.name": "Reverse",
        "effect.stun.name": "Bound",
        "effect.shield.name": "Shield",
    },
    "zh": {
        "start.subtitle": "鼠标与快捷键菜单：选择开局模式。",
        "start.note": "新版保留旧原型作为资源，按新的游戏流程重新搭建。",
        "language": "语言",
        "language.en": "英文",
        "language.zh": "中文",
        "mode.local": "同屏双人",
        "mode.host": "联网建房",
        "mode.join": "联网加入",
        "guide.title": "操作指南",
        "guide.subtitle": "玩家操作指南",
        "guide.doc_note": "完整文档：docs/玩家操作指南.md",
        "quit": "退出",
        "config.subtitle": "地图、视野与模式配置",
        "back": "返回",
        "continue": "继续",
        "start": "开始",
        "preset.small": "小型",
        "preset.medium": "中型",
        "preset.large": "大型",
        "slider.width": "宽度",
        "slider.height": "高度",
        "slider.loop": "环路复杂度",
        "slider.overlap": "重合率",
        "slider.trap": "陷阱等级",
        "slider.pushable": "可推墙等级",
        "slider.danger": "危险区等级",
        "fog.heavy": "重雾",
        "fog.light": "轻雾",
        "fog.none": "无雾",
        "players.n": "{count} 人",
        "toggle.collision": "碰撞",
        "toggle.trail": "拖尾",
        "config.note": "环路复杂度控制寻路难度；陷阱、可推墙、危险区是独立地图特色。",
        "summary.size": "尺寸",
        "summary.loop": "环路复杂度",
        "summary.overlap": "重合率",
        "summary.fog": "雾",
        "summary.players": "玩家数",
        "summary.features": "特色",
        "roles.subtitle": "角色选择。技能数值后续可继续平衡。",
        "roles.tip": "提示：角色目前是临时预设，最终可在平衡测试后重新绑定技能。",
        "join.subtitle": "加入联网房间",
        "join.host_ip": "主机 IP",
        "join.connect": "连接",
        "playing.waiting_state": "等待同步状态...",
        "lobby.subtitle": "联网大厅：Enter 准备，Backspace 取消准备。",
        "lobby.connecting": "连接中...",
        "lobby.you_are": "你是 P{pid}",
        "lobby.ready": "已准备",
        "lobby.not_ready": "未准备",
        "lobby.waiting": "等待中",
        "lobby.note": "所有配置玩家连接并准备后，主机会自动开始游戏。",
        "hud.enemy_intel": "对手情报",
        "hud.no_scan": "未扫描",
        "hud.progress_board": "进度榜",
        "hud.tasks": "任务",
        "hud.target": "目标",
        "hud.fruit": "果实",
        "hud.goal": "终点",
        "hud.unknown": "未知",
        "hud.locked": "未解锁",
        "hud.enemy_goal": "对手终点",
        "hud.effects": "效果",
        "hud.tasks_panel": "任务",
        "hud.required_short": "必做",
        "hud.bonus_short": "奖励",
        "hud.skills": "技能",
        "hud.start_in": "开局倒计时",
        "hud.done": "完成",
        "hud.foes": "名对手",
        "result.wins": "{name} 获胜！",
        "result.prompt": "按 R 返回菜单，按 ESC 退出",
        "role.explorer.name": "探索者",
        "role.explorer.summary": "视野与路线控制",
        "role.saboteur.name": "干扰者",
        "role.saboteur.summary": "减速、反向与假奖励",
        "role.breaker.name": "破壁者",
        "role.breaker.summary": "移动与墙体控制",
        "role.trapper.name": "陷阱师",
        "role.trapper.summary": "区域、陷阱与偷取",
        "role.analyst.name": "分析师",
        "role.analyst.summary": "对手情报与隐匿",
        "skill.reveal_own_area.name": "己方扫描",
        "skill.reveal_enemy_area.name": "对手扫描",
        "skill.reveal_enemy_pos.name": "追踪",
        "skill.hide_self.name": "隐匿",
        "skill.reveal_own_goal.name": "己方终点",
        "skill.reveal_enemy_goal.name": "对手终点",
        "skill.break_wall.name": "破墙",
        "skill.perm_break.name": "永久破墙",
        "skill.build_wall.name": "造墙",
        "skill.perm_build.name": "永久造墙",
        "skill.move_enemy_goal.name": "移终点",
        "skill.blind_enemy.name": "缩视野",
        "skill.fake_fruit.name": "假果",
        "skill.speed_up.name": "加速",
        "skill.slow_enemy.name": "减速",
        "skill.confuse_enemy.name": "反向",
        "skill.trap_area.name": "陷阱",
        "skill.stun_enemy.name": "禁锢",
        "skill.shield.name": "护盾",
        "skill.teleport.name": "闪现",
        "skill.steal.name": "偷取",
        "task.fruit.name": "收集果实",
        "task.shape.name": "完成4次转向",
        "task.loop_length.name": "闭合环路",
        "task.unique_loops.name": "不同环路",
        "task.opponent_trap.name": "诱导踩陷阱",
        "task.meet.name": "与对手相遇",
        "effect.hidden.name": "隐匿",
        "effect.blind.name": "视野缩小",
        "effect.haste.name": "加速",
        "effect.slow.name": "减速",
        "effect.confuse.name": "反向",
        "effect.stun.name": "禁锢",
        "effect.shield.name": "护盾",
    },
}


STATUS_MESSAGES_ZH = {
    "Enemy built a wall": "对手建造了一段墙",
    "Fake fruit appeared": "出现假果实",
    "Trap area placed": "陷阱区域已生成",
    "A fruit was stolen": "一个果实被偷走",
    "Your goal moved": "你的终点被移动",
    "Trap triggered": "触发陷阱",
    "Fake fruit slowed you": "假果实使你减速",
    "Danger zone": "危险区域",
    "Hidden": "已隐匿",
    "Vision reduced": "视野缩小",
    "Speed up": "速度提升",
    "Slowed": "已减速",
    "Controls reversed": "操作反向",
    "Bound": "被禁锢",
    "Shielded": "护盾生效",
    "Skill cooling down": "技能冷却中",
    "Target occupied": "目标格已有玩家",
    "Out of range": "超出释放范围",
    "Enemy out of range": "目标对手超出范围",
    "No target player": "没有选中目标玩家",
    "No skill in slot": "该技能位为空",
    "Need a target cell": "需要选择目标格",
    "Out of maze": "超出地图范围",
    "No target maze": "没有目标迷宫",
    "Game ended": "游戏已结束",
    "Unknown action": "未知操作",
    "Goal locked": "终点尚未解锁",
    "Select target cell": "请选择释放格",
    "Click your map": "请点击己方地图",
    "Click an opponent map": "请点击对手地图",
}


def normalize_language(language: str | None) -> str:
    language = (language or "en").lower()
    if language.startswith("zh") or language in {"cn", "chinese"}:
        return "zh"
    return "en"


def tr(key: str, language: str | None = "en", fallback: str | None = None, **kwargs) -> str:
    lang = normalize_language(language)
    text = TEXT.get(lang, {}).get(key) or TEXT["en"].get(key) or fallback or key
    if kwargs:
        return text.format(**kwargs)
    return text


def role_name(role_id: str, fallback: str, language: str | None = "en") -> str:
    return tr(f"role.{role_id}.name", language, fallback)


def role_summary(role_id: str, fallback: str, language: str | None = "en") -> str:
    return tr(f"role.{role_id}.summary", language, fallback)


def skill_name(skill_id: str, fallback: str, language: str | None = "en") -> str:
    return tr(f"skill.{skill_id}.name", language, fallback)


def task_name(task_id: str, fallback: str, language: str | None = "en") -> str:
    return tr(f"task.{task_id}.name", language, fallback)


def effect_name(effect_id: str, language: str | None = "en") -> str:
    return tr(f"effect.{effect_id}.name", language, effect_id)


def _english_name_lookup(prefix: str) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for key, value in TEXT["en"].items():
        parts = key.split(".")
        if len(parts) == 3 and parts[0] == prefix and parts[2] == "name":
            lookup[value] = parts[1]
    return lookup


_SKILL_BY_ENGLISH = _english_name_lookup("skill")
_TASK_BY_ENGLISH = _english_name_lookup("task")


def _localized_skill_from_english(name: str, language: str | None) -> str:
    skill_id = _SKILL_BY_ENGLISH.get(name)
    if not skill_id:
        return name
    return skill_name(skill_id, name, language)


def _localized_task_from_english(name: str, language: str | None) -> str:
    task_id = _TASK_BY_ENGLISH.get(name)
    if not task_id:
        return name
    return task_name(task_id, name, language)


def message_text(message: str, language: str | None = "en") -> str:
    if normalize_language(language) != "zh":
        return message
    return STATUS_MESSAGES_ZH.get(message, message)


def event_text(text: str, language: str | None = "en") -> str:
    if normalize_language(language) != "zh":
        return text

    if text == "All players ready":
        return "所有玩家已准备"

    match = re.fullmatch(r"P(\d+) used (.+)", text)
    if match:
        return f"P{match.group(1)} 使用 {_localized_skill_from_english(match.group(2), language)}"

    match = re.fullmatch(r"P(\d+) collected fruit", text)
    if match:
        return f"P{match.group(1)} 收集果实"

    match = re.fullmatch(r"P(\d+) took fake fruit", text)
    if match:
        return f"P{match.group(1)} 吃到假果实"

    match = re.fullmatch(r"P(\d+) triggered trap", text)
    if match:
        return f"P{match.group(1)} 触发陷阱"

    match = re.fullmatch(r"P(\d+) pushed a wall", text)
    if match:
        return f"P{match.group(1)} 推动墙体"

    match = re.fullmatch(r"P(\d+) met P(\d+)", text)
    if match:
        return f"P{match.group(1)} 与 P{match.group(2)} 相遇"

    match = re.fullmatch(r"P(\d+) completed (.+)", text)
    if match:
        return f"P{match.group(1)} 完成 {_localized_task_from_english(match.group(2), language)}"

    match = re.fullmatch(r"P(\d+) gained (.+)", text)
    if match:
        return f"P{match.group(1)} 获得 {_localized_skill_from_english(match.group(2), language)}"

    match = re.fullmatch(r"P(\d+) moved P(\d+)'s goal", text)
    if match:
        return f"P{match.group(1)} 移动了 P{match.group(2)} 的终点"

    match = re.fullmatch(r"P(\d+) wins!", text)
    if match:
        return f"P{match.group(1)} 获胜！"

    match = re.fullmatch(r"P(\d+) disconnected", text)
    if match:
        return f"P{match.group(1)} 断开连接"

    match = re.fullmatch(r"P(\d+) reconnected", text)
    if match:
        return f"P{match.group(1)} 重新连接"

    return message_text(text, language)
