from __future__ import annotations

import asyncio
import time
import secrets
import string
from dataclasses import dataclass, field
from typing import Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .ai import choose_pass, choose_play
from .game import HeartsGame, PlayerState, PASS_LEFT, PASS_RIGHT, PASS_ACROSS, PASS_HOLD

app = FastAPI()

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@dataclass
class Room:
    id: str
    max_players: int = 4
    players: Dict[str, PlayerState] = field(default_factory=dict)
    host_id: Optional[str] = None
    game: Optional[HeartsGame] = None
    connections: Dict[str, WebSocket] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    next_action_at: float = 0.0
    bot_task: Optional[asyncio.Task] = None

    def add_player(self, name: str, is_bot: bool = False) -> Optional[PlayerState]:
        if len(self.players) >= self.max_players:
            return None
        if self.game and self.game.state.phase != "lobby":
            return None

        player_id = secrets.token_hex(4)
        player = PlayerState(id=player_id, name=name, is_bot=is_bot)
        self.players[player_id] = player
        if not self.host_id:
            self.host_id = player_id
        return player

    def remove_player(self, player_id: str) -> None:
        if player_id in self.connections:
            self.connections.pop(player_id, None)
        if self.game and self.game.state.phase != "lobby":
            player = self.players.get(player_id)
            if player:
                player.is_bot = True
            return
        if player_id in self.players:
            self.players.pop(player_id, None)
        if self.host_id == player_id:
            self.host_id = next(iter(self.players), None)


def room_id() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(6))


rooms: Dict[str, Room] = {}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse("app/static/index.html")


@app.get("/room/{room_id}")
async def room_page(room_id: str) -> FileResponse:
    return FileResponse("app/static/index.html")


@app.post("/api/rooms")
async def create_room() -> JSONResponse:
    rid = room_id()
    rooms[rid] = Room(id=rid)
    return JSONResponse({"room_id": rid})


@app.websocket("/ws/{room_id}")
async def room_socket(websocket: WebSocket, room_id: str, name: Optional[str] = None) -> None:
    room = rooms.get(room_id)
    if not room:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    player_name = (name or "Player").strip()[:20]

    async with room.lock:
        player = room.add_player(player_name)
        if not player:
            await websocket.close(code=1008)
            return
        room.connections[player.id] = websocket

    await send_state(room, player.id)
    await broadcast_state(room)

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("type")
            async with room.lock:
                if action == "add_bot":
                    if player.id == room.host_id:
                        bot_name = f"Bot {len([p for p in room.players.values() if p.is_bot]) + 1}"
                        room.add_player(bot_name, is_bot=True)
                elif action == "start_game":
                    if player.id == room.host_id and len(room.players) == room.max_players:
                        room.game = HeartsGame(list(room.players.values()))
                        room.game.start_round()
                        room.next_action_at = 0.0
                elif action == "start_round":
                    if player.id == room.host_id and room.game:
                        room.game.start_next_round()
                        room.next_action_at = 0.0
                elif action == "pass_cards" and room.game:
                    cards = data.get("cards", [])
                    room.game.submit_pass(player.id, cards)
                    if room.game.state.phase == "playing":
                        schedule_bot_tick(room, 0.8)
                elif action == "play_card" and room.game:
                    before_trick = len(room.game.state.trick)
                    card = data.get("card")
                    if card:
                        played = room.game.play_card(player.id, card)
                        if played:
                            delay = 0.8
                            if before_trick == len(room.players) - 1 and not room.game.state.trick:
                                delay = 2.0
                            schedule_bot_tick(room, delay)

                await advance_bots(room)

            await broadcast_state(room)

    except WebSocketDisconnect:
        async with room.lock:
            room.remove_player(player.id)
        await broadcast_state(room)


def pass_dir_label(pass_dir: int) -> str:
    if pass_dir == PASS_LEFT:
        return "left"
    if pass_dir == PASS_RIGHT:
        return "right"
    if pass_dir == PASS_ACROSS:
        return "across"
    return "hold"


async def send_state(room: Room, player_id: str) -> None:
    ws = room.connections.get(player_id)
    if not ws:
        return

    game = room.game
    players = [
        {
            "id": p.id,
            "name": p.name,
            "is_bot": p.is_bot,
            "score": game.state.scores.get(p.id, 0) if game else 0,
        }
        for p in room.players.values()
    ]

    state = {
        "room_id": room.id,
        "max_players": room.max_players,
        "host_id": room.host_id,
        "phase": game.state.phase if game else "lobby",
        "round": game.state.round_index if game else 0,
        "pass_dir": pass_dir_label(game.state.pass_dir) if game else "left",
        "players": players,
        "trick": [],
        "current_turn": game.state.current_turn if game else None,
        "hearts_broken": game.state.hearts_broken if game else False,
        "scores": game.state.scores if game else {},
        "your_id": player_id,
        "hand": game.state.hands.get(player_id, []) if game else [],
        "legal_moves": game.get_legal_moves(player_id) if game and game.state.phase == "playing" else [],
        "pending_pass": bool(game and game.state.phase == "passing" and player_id not in game.state.pending_pass),
        "can_start": player_id == room.host_id,
    }

    if game:
        trick_view = game.state.trick or game.state.last_trick
        state["trick"] = [
            {
                "player_id": pid,
                "player_name": room.players[pid].name,
                "card": card,
            }
            for pid, card in trick_view
        ]

    await ws.send_json({"type": "state", "state": state})


async def broadcast_state(room: Room) -> None:
    for pid in list(room.connections.keys()):
        await send_state(room, pid)

def schedule_bot_tick(room: Room, delay: float) -> None:
    room.next_action_at = time.monotonic() + max(0.0, delay)
    if room.bot_task and not room.bot_task.done():
        room.bot_task.cancel()

    async def _runner() -> None:
        await asyncio.sleep(max(0.0, delay))
        async with room.lock:
            await advance_bots(room)
        await broadcast_state(room)

    room.bot_task = asyncio.create_task(_runner())


async def advance_bots(room: Room) -> None:
    game = room.game
    if not game:
        return

    now = time.monotonic()
    if now < room.next_action_at:
        return

    if game.state.phase == "passing":
        for pid, player in room.players.items():
            if player.is_bot and pid not in game.state.pending_pass:
                hand = game.state.hands.get(pid, [])
                cards = choose_pass(hand)
                game.submit_pass(pid, cards)
        if game.state.phase == "playing":
            schedule_bot_tick(room, 0.8)
        return

    if game.state.phase != "playing":
        return

    current = game.state.current_turn
    if not current:
        return
    player = room.players.get(current)
    if not player or not player.is_bot:
        return

    before_trick = len(game.state.trick)
    legal = game.get_legal_moves(current)
    if not legal:
        return
    card = choose_play(legal)
    game.play_card(current, card)

    delay = 0.8
    if before_trick == len(room.players) - 1 and not game.state.trick:
        delay = 2.0
    room.next_action_at = time.monotonic() + delay
    schedule_bot_tick(room, delay)
