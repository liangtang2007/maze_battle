from __future__ import annotations

import json
import socket
import threading
from dataclasses import dataclass, field
from typing import Any

from engine import GameConfig, GameState, ROLES


def encode(msg: dict[str, Any]) -> bytes:
    return (json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8")


class LineBuffer:
    def __init__(self):
        self.buf = b""

    def feed(self, data: bytes) -> list[dict[str, Any]]:
        self.buf += data
        out = []
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            if not line:
                continue
            try:
                out.append(json.loads(line.decode("utf-8")))
            except json.JSONDecodeError:
                continue
        return out


@dataclass
class ClientConn:
    sock: socket.socket
    addr: tuple
    pid: int
    buffer: LineBuffer
    alive: bool = True

    def send(self, msg: dict[str, Any]) -> None:
        try:
            self.sock.sendall(encode(msg))
        except OSError:
            self.alive = False


@dataclass
class LobbyStatus:
    player_count: int
    roles: list[str]
    ready: dict[int, bool] = field(default_factory=dict)
    connected: dict[int, bool] = field(default_factory=dict)
    game_started: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "player_count": self.player_count,
            "roles": self.roles,
            "ready": {str(k): v for k, v in self.ready.items()},
            "connected": {str(k): v for k, v in self.connected.items()},
            "game_started": self.game_started,
        }


class HostSession:
    def __init__(self, config: GameConfig, roles: list[str]):
        self.config = config.normalize()
        self.host_pid = 0
        self.sock: socket.socket | None = None
        self.clients: dict[int, ClientConn] = {}
        self.running = False
        self.lock = threading.Lock()
        self.pending_inputs: list[tuple[int, dict[str, Any]]] = []
        self.state: GameState | None = None
        role_list = list(roles[: self.config.player_count])
        while len(role_list) < self.config.player_count:
            role_list.append("explorer")
        self.lobby = LobbyStatus(
            player_count=self.config.player_count,
            roles=role_list,
            ready={0: False},
            connected={0: True},
        )

    def start(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", self.config.port))
        self.sock.listen(self.config.player_count)
        self.running = True
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def stop(self) -> None:
        self.running = False
        with self.lock:
            for client in self.clients.values():
                try:
                    client.sock.close()
                except OSError:
                    pass
            self.clients.clear()
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass

    def _accept_loop(self) -> None:
        while self.running:
            try:
                conn, addr = self.sock.accept()
                with self.lock:
                    pid = self._first_available_pid()
                    if pid is None:
                        conn.sendall(encode({"type": "reject", "reason": "Room full"}))
                        conn.close()
                        continue
                    client = ClientConn(conn, addr, pid, LineBuffer())
                    self.clients[pid] = client
                    self.lobby.connected[pid] = True
                    self.lobby.ready[pid] = False
                    client.send({"type": "assign", "pid": pid, "lobby": self.lobby.as_dict()})
                    if self.state is not None:
                        client.send({"type": "snapshot", "snapshot": self.state.to_snapshot()})
                threading.Thread(target=self._recv_loop, args=(pid,), daemon=True).start()
                if self.state:
                    self.state.add_event(f"P{pid + 1} reconnected")
            except OSError:
                break

    def _first_available_pid(self) -> int | None:
        for pid in range(1, self.config.player_count):
            if not self.lobby.connected.get(pid, False):
                return pid
        return None

    def _recv_loop(self, pid: int) -> None:
        client = self.clients.get(pid)
        if not client:
            return
        while self.running and client.alive:
            try:
                data = client.sock.recv(65536)
                if not data:
                    break
                for msg in client.buffer.feed(data):
                    self._handle_client_msg(pid, msg)
            except OSError:
                break
        with self.lock:
            self.clients.pop(pid, None)
            self.lobby.connected[pid] = False
            self.lobby.ready[pid] = False
        if self.state:
            self.state.add_event(f"P{pid + 1} disconnected")

    def _handle_client_msg(self, pid: int, msg: dict[str, Any]) -> None:
        mtype = msg.get("type")
        if mtype == "hello":
            role_id = msg.get("role_id", "explorer")
            self.set_role(pid, role_id)
        elif mtype == "ready":
            self.set_ready(pid, bool(msg.get("ready", True)))
        elif mtype == "input":
            with self.lock:
                self.pending_inputs.append((pid, msg.get("payload", {})))

    def set_role(self, pid: int, role_id: str) -> None:
        if role_id not in ROLES:
            role_id = "explorer"
        with self.lock:
            if 0 <= pid < self.config.player_count and not self.lobby.game_started:
                self.lobby.roles[pid] = role_id

    def set_ready(self, pid: int, ready: bool) -> None:
        with self.lock:
            if 0 <= pid < self.config.player_count:
                self.lobby.ready[pid] = ready

    def local_input(self, payload: dict[str, Any]) -> None:
        with self.lock:
            self.pending_inputs.append((self.host_pid, payload))

    def update(self, dt: float) -> None:
        with self.lock:
            inputs = list(self.pending_inputs)
            self.pending_inputs.clear()
        if not self.lobby.game_started:
            for pid, payload in inputs:
                if payload.get("action") == "ready":
                    self.set_ready(pid, bool(payload.get("ready", True)))
                elif payload.get("action") == "role":
                    self.set_role(pid, payload.get("role_id", "explorer"))
            self._maybe_start_game()
            self.broadcast_lobby()
            return

        if self.state:
            for pid, payload in inputs:
                apply_input(self.state, pid, payload)
            self.state.update(dt)
            self.broadcast_snapshot()

    def _maybe_start_game(self) -> None:
        expected = set(range(self.config.player_count))
        connected = {pid for pid, ok in self.lobby.connected.items() if ok}
        ready = {pid for pid, ok in self.lobby.ready.items() if ok}
        if expected <= connected and expected <= ready:
            self.state = GameState(self.config, self.lobby.roles)
            self.lobby.game_started = True
            self.state.add_event("All players ready")

    def broadcast_lobby(self) -> None:
        msg = {"type": "lobby", "lobby": self.lobby.as_dict()}
        with self.lock:
            for client in list(self.clients.values()):
                client.send(msg)

    def broadcast_snapshot(self) -> None:
        if not self.state:
            return
        msg = {"type": "snapshot", "snapshot": self.state.to_snapshot(), "lobby": self.lobby.as_dict()}
        with self.lock:
            dead = []
            for pid, client in self.clients.items():
                client.send(msg)
                if not client.alive:
                    dead.append(pid)
            for pid in dead:
                self.clients.pop(pid, None)


class ClientSession:
    def __init__(self, host: str, port: int, role_id: str = "explorer"):
        self.host = host
        self.port = port
        self.role_id = role_id
        self.sock: socket.socket | None = None
        self.buffer = LineBuffer()
        self.running = False
        self.pid: int | None = None
        self.state: GameState | None = None
        self.lobby: dict[str, Any] | None = None
        self.error: str = ""
        self.lock = threading.Lock()

    def connect(self) -> bool:
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            self.running = True
            self.sock.sendall(encode({"type": "hello", "role_id": self.role_id}))
            threading.Thread(target=self._recv_loop, daemon=True).start()
            return True
        except OSError as exc:
            self.error = str(exc)
            return False

    def disconnect(self) -> None:
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass

    def _recv_loop(self) -> None:
        while self.running:
            try:
                data = self.sock.recv(65536)
                if not data:
                    break
                for msg in self.buffer.feed(data):
                    self._handle(msg)
            except OSError as exc:
                self.error = str(exc)
                break
        self.running = False

    def _handle(self, msg: dict[str, Any]) -> None:
        with self.lock:
            if msg.get("type") == "assign":
                self.pid = msg.get("pid")
                self.lobby = msg.get("lobby")
            elif msg.get("type") == "lobby":
                self.lobby = msg.get("lobby")
            elif msg.get("type") == "snapshot":
                if msg.get("lobby"):
                    self.lobby = msg.get("lobby")
                self.state = GameState.from_snapshot(msg["snapshot"])
            elif msg.get("type") == "reject":
                self.error = msg.get("reason", "Rejected")
                self.running = False

    def send_role(self, role_id: str) -> None:
        self.role_id = role_id
        self._send({"type": "hello", "role_id": role_id})

    def send_ready(self, ready: bool = True) -> None:
        self._send({"type": "ready", "ready": ready})

    def send_input(self, payload: dict[str, Any]) -> None:
        self._send({"type": "input", "payload": payload})

    def _send(self, msg: dict[str, Any]) -> None:
        if not self.sock or not self.running:
            return
        try:
            self.sock.sendall(encode(msg))
        except OSError as exc:
            self.error = str(exc)
            self.running = False


def apply_input(state: GameState, pid: int, payload: dict[str, Any]) -> tuple[bool, str]:
    action = payload.get("action")
    if action == "move":
        return state.command_move(pid, int(payload.get("dx", 0)), int(payload.get("dy", 0))), ""
    elif action == "skill":
        target = payload.get("target")
        if target is not None:
            target = (int(target[0]), int(target[1]))
        target_pid = payload.get("target_pid")
        if target_pid is not None:
            target_pid = int(target_pid)
        ok, message = state.cast_skill(pid, int(payload.get("slot", 0)), target, target_pid)
        if not ok and 0 <= pid < len(state.players):
            state.players[pid].status_message = message
            state.players[pid].status_timer = 2.0
        return ok, message
    elif action == "mark":
        target = payload.get("target")
        state.add_mark(pid, tuple(target) if target else None)
        return True, ""
    return False, "Unknown action"
