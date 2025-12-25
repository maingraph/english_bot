"""
Telegram Mini App (TMA) backend server.
Serves the web frontend and provides real-time game state via REST/SSE.
"""
import asyncio
import hashlib
import hmac
import html
import json
import os
import time
import urllib.parse
from typing import Any, Dict, List, Optional

from aiohttp import web

from .config import ADMIN_TOKEN, BOT_TOKEN, TASK_TYPES, log
from .runtime import db

# ---------------------------------------------------------------------------
# In-memory game state for the TMA classroom game (single active game)
# ---------------------------------------------------------------------------

class ClassroomGame:
    """Single classroom game instance."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.is_open = False          # Lobby open for joining?
        self.is_running = False       # Game in progress?
        self.is_finished = False      # Game ended?
        self.players: Dict[int, Dict[str, Any]] = {}  # user_id -> {name, score, correct, wrong}
        self.current_round = 0
        self.total_rounds = 10
        self.round_seconds = 12
        self.current_question: Optional[Dict[str, Any]] = None
        self.round_start_time: float = 0
        self.answers: Dict[int, Dict[str, Any]] = {}  # user_id -> {choice, time}
        self.task_type = "SYNONYM"
        self.round_results: List[Dict[str, Any]] = []

    def open_lobby(self, total_rounds: int = 10, round_seconds: int = 12):
        self.reset()
        self.is_open = True
        self.total_rounds = total_rounds
        self.round_seconds = round_seconds

    def join(self, user_id: int, name: str) -> bool:
        if not self.is_open or self.is_running or self.is_finished:
            return False
        if user_id not in self.players:
            self.players[user_id] = {
                "name": name,
                "score": 0,
                "correct": 0,
                "wrong": 0,
            }
        return True

    def player_count(self) -> int:
        return len(self.players)

    def start_game(self) -> bool:
        if not self.is_open or self.is_running or len(self.players) < 1:
            return False
        self.is_open = False
        self.is_running = True
        self.current_round = 0
        return True

    def next_round(self) -> bool:
        if not self.is_running or self.is_finished:
            return False

        self.current_round += 1
        if self.current_round > self.total_rounds:
            self.is_running = False
            self.is_finished = True
            return False

        # Pick task type (rotate)
        self.task_type = TASK_TYPES[(self.current_round - 1) % len(TASK_TYPES)]
        
        # Build question
        q = db.build_question(self.task_type, k_options=4)
        if not q:
            # Fallback to any type
            for t in TASK_TYPES:
                q = db.build_question(t, k_options=4)
                if q:
                    self.task_type = t
                    break
        
        if not q:
            self.is_running = False
            self.is_finished = True
            return False

        self.current_question = q
        self.round_start_time = time.time()
        self.answers = {}
        return True

    def submit_answer(self, user_id: int, choice: int) -> bool:
        if not self.is_running or user_id not in self.players:
            return False
        if user_id in self.answers:
            return False  # Already answered
        if not self.current_question:
            return False

        latency_ms = int((time.time() - self.round_start_time) * 1000)
        self.answers[user_id] = {"choice": choice, "time": latency_ms}
        return True

    def all_answered(self) -> bool:
        return len(self.answers) >= len(self.players)

    def time_remaining(self) -> float:
        if not self.is_running or not self.current_question:
            return 0
        elapsed = time.time() - self.round_start_time
        return max(0, self.round_seconds - elapsed)

    def end_round(self) -> Dict[str, Any]:
        """Score round and return results."""
        if not self.current_question:
            return {}

        correct_idx = self.current_question["correct_idx"]
        correct_text = self.current_question["options"][correct_idx]
        
        results = {
            "round": self.current_round,
            "correct_answer": correct_text,
            "correct_idx": correct_idx,
            "player_results": [],
        }

        for uid, player in self.players.items():
            ans = self.answers.get(uid)
            if ans is None:
                # No answer = wrong
                player["wrong"] += 1
                results["player_results"].append({
                    "user_id": uid,
                    "name": player["name"],
                    "correct": False,
                    "points": 0,
                    "time_ms": None,
                })
            else:
                is_correct = ans["choice"] == correct_idx
                # Points: 2 for fast correct, 1 for slow correct, 0 for wrong
                if is_correct:
                    pts = 2 if ans["time"] <= 5000 else 1
                    player["correct"] += 1
                else:
                    pts = 0
                    player["wrong"] += 1
                player["score"] += pts
                results["player_results"].append({
                    "user_id": uid,
                    "name": player["name"],
                    "correct": is_correct,
                    "points": pts,
                    "time_ms": ans["time"],
                })

        self.round_results.append(results)
        self.current_question = None
        return results

    def get_leaderboard(self, top_n: int = 10) -> List[Dict[str, Any]]:
        sorted_players = sorted(
            self.players.items(),
            key=lambda x: (-x[1]["score"], -x[1]["correct"]),
        )
        return [
            {"rank": i + 1, "user_id": uid, **data}
            for i, (uid, data) in enumerate(sorted_players[:top_n])
        ]

    def get_full_leaderboard(self) -> List[Dict[str, Any]]:
        sorted_players = sorted(
            self.players.items(),
            key=lambda x: (-x[1]["score"], -x[1]["correct"]),
        )
        return [
            {"rank": i + 1, "user_id": uid, **data}
            for i, (uid, data) in enumerate(sorted_players)
        ]

    def get_player_rank(self, user_id: int) -> Optional[int]:
        sorted_players = sorted(
            self.players.items(),
            key=lambda x: (-x[1]["score"], -x[1]["correct"]),
        )
        for i, (uid, _) in enumerate(sorted_players):
            if uid == user_id:
                return i + 1
        return None

    def to_state_dict(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """Return current state for frontend."""
        state = {
            "is_open": self.is_open,
            "is_running": self.is_running,
            "is_finished": self.is_finished,
            "player_count": len(self.players),
            "current_round": self.current_round,
            "total_rounds": self.total_rounds,
            "round_seconds": self.round_seconds,
            "time_remaining": self.time_remaining(),
            "leaderboard": self.get_leaderboard(5),
        }

        if user_id and user_id in self.players:
            state["my_rank"] = self.get_player_rank(user_id)
            state["my_score"] = self.players[user_id]["score"]
            state["my_correct"] = self.players[user_id]["correct"]
            state["my_wrong"] = self.players[user_id]["wrong"]
            state["already_answered"] = user_id in self.answers

        if self.current_question and self.is_running:
            state["question"] = {
                "prompt": self.current_question["prompt"],
                "options": self.current_question["options"],
                "task_type": self.task_type,
            }

        if self.is_finished:
            state["final_leaderboard"] = self.get_full_leaderboard()

        return state


# Singleton game instance
game = ClassroomGame()

# Background task for round timer
_round_task: Optional[asyncio.Task] = None


async def round_timer_loop(app: web.Application):
    """Background loop that auto-ends rounds when time expires."""
    global game
    while True:
        await asyncio.sleep(0.5)
        if game.is_running and game.current_question:
            if game.time_remaining() <= 0 or game.all_answered():
                game.end_round()
                await asyncio.sleep(2)  # Brief pause between rounds
                if not game.next_round():
                    # Game finished
                    pass


# ---------------------------------------------------------------------------
# Telegram WebApp auth validation
# ---------------------------------------------------------------------------

def validate_init_data(init_data: str) -> Optional[Dict[str, Any]]:
    """Validate Telegram WebApp initData and extract user info."""
    if not BOT_TOKEN:
        return None

    try:
        parsed = urllib.parse.parse_qs(init_data)
        data_check_string_parts = []
        received_hash = None

        for key in sorted(parsed.keys()):
            if key == "hash":
                received_hash = parsed[key][0]
            else:
                data_check_string_parts.append(f"{key}={parsed[key][0]}")

        if not received_hash:
            return None

        data_check_string = "\n".join(data_check_string_parts)
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        if computed_hash != received_hash:
            log.warning("TMA auth failed: hash mismatch")
            return None

        # Extract user
        if "user" in parsed:
            user_data = json.loads(parsed["user"][0])
            return user_data
        return None

    except Exception as e:
        log.warning(f"TMA auth error: {e}")
        return None


# ---------------------------------------------------------------------------
# HTTP handlers
# ---------------------------------------------------------------------------

async def handle_index(request: web.Request) -> web.Response:
    """Serve the main TMA HTML."""
    html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(html_path):
        return web.FileResponse(html_path)
    return web.Response(text="TMA index.html not found", status=404)


async def handle_state(request: web.Request) -> web.Response:
    """Get current game state."""
    user_id = None
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    if init_data:
        user = validate_init_data(init_data)
        if user:
            user_id = user.get("id")

    state = game.to_state_dict(user_id)
    return web.json_response(state)


async def handle_join(request: web.Request) -> web.Response:
    """Join the game lobby."""
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    user = validate_init_data(init_data)
    if not user:
        return web.json_response({"ok": False, "error": "Invalid auth"}, status=401)

    user_id = user.get("id")
    name = user.get("first_name", "Player")
    if user.get("last_name"):
        name += " " + user.get("last_name")

    ok = game.join(user_id, name)
    return web.json_response({"ok": ok})


async def handle_answer(request: web.Request) -> web.Response:
    """Submit answer for current round."""
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    user = validate_init_data(init_data)
    if not user:
        return web.json_response({"ok": False, "error": "Invalid auth"}, status=401)

    try:
        body = await request.json()
        choice = int(body.get("choice", -1))
    except:
        return web.json_response({"ok": False, "error": "Invalid body"}, status=400)

    user_id = user.get("id")
    ok = game.submit_answer(user_id, choice)
    return web.json_response({"ok": ok})


# Admin endpoints (simple token-based for classroom use)


def check_admin(request: web.Request) -> bool:
    token = request.headers.get("X-Admin-Token", "")
    return token == ADMIN_TOKEN


async def handle_admin_open(request: web.Request) -> web.Response:
    """Admin: open lobby for joining."""
    if not check_admin(request):
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=403)

    try:
        body = await request.json()
        rounds = int(body.get("rounds", 10))
        seconds = int(body.get("seconds", 12))
    except:
        rounds, seconds = 10, 12

    game.open_lobby(rounds, seconds)
    return web.json_response({"ok": True})


async def handle_admin_start(request: web.Request) -> web.Response:
    """Admin: start the game."""
    if not check_admin(request):
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=403)

    ok = game.start_game()
    if ok:
        game.next_round()
    return web.json_response({"ok": ok})


async def handle_admin_reset(request: web.Request) -> web.Response:
    """Admin: reset game to initial state."""
    if not check_admin(request):
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=403)

    game.reset()
    return web.json_response({"ok": True})


async def handle_admin_next(request: web.Request) -> web.Response:
    """Admin: manually advance to next round."""
    if not check_admin(request):
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=403)

    if game.current_question:
        game.end_round()
    ok = game.next_round()
    return web.json_response({"ok": ok})


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_tma_app() -> web.Application:
    app = web.Application()

    # Routes
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/state", handle_state)
    app.router.add_post("/api/join", handle_join)
    app.router.add_post("/api/answer", handle_answer)

    # Admin routes
    app.router.add_post("/api/admin/open", handle_admin_open)
    app.router.add_post("/api/admin/start", handle_admin_start)
    app.router.add_post("/api/admin/reset", handle_admin_reset)
    app.router.add_post("/api/admin/next", handle_admin_next)

    # Static files
    static_path = os.path.join(os.path.dirname(__file__), "static")
    if os.path.isdir(static_path):
        app.router.add_static("/static/", static_path, name="static")

    # Background task
    async def start_background(app):
        global _round_task
        _round_task = asyncio.create_task(round_timer_loop(app))

    async def stop_background(app):
        global _round_task
        if _round_task:
            _round_task.cancel()
            try:
                await _round_task
            except asyncio.CancelledError:
                pass

    app.on_startup.append(start_background)
    app.on_cleanup.append(stop_background)

    return app


def run_tma_server(host: str = "0.0.0.0", port: int = 8080):
    """Run the TMA server standalone."""
    app = create_tma_app()
    log.info(f"Starting TMA server on {host}:{port}")
    web.run_app(app, host=host, port=port)

