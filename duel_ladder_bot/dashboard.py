import html
import time

from telegram.ext import ContextTypes

from .config import GLOBAL_CHAT_ID
from .helpers import current_task_type, display_name
from .keyboards import reply_kb_main
from .runtime import db
from . import state


async def send_dashboard(
    chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE
) -> None:
    ev = db.get_active_event(chat_id=GLOBAL_CHAT_ID)
    lines = ["<b>🎯 Duel Ladder</b>", ""]
    if not ev:
        lines += [
            "⛔ <b>No active event</b>",
            "",
            "Ask the host to start one (admin):",
            "• /event_start 10 120",
            "",
            "Then tap:",
            "• 🎮 <b>Join & Play</b>",
        ]
        await context.bot.send_message(
            chat_id=chat_id,
            text="\n".join(lines),
            parse_mode="HTML",
            reply_markup=reply_kb_main(),
        )
        return

    event_id = int(ev["id"])
    remaining = max(0, int(ev["ends_at"]) - int(time.time()))
    mins, secs = remaining // 60, remaining % 60

    joined = db.get_player_stats(event_id=event_id, user_id=user_id) is not None
    autoq = db.get_auto_queue(event_id=event_id, user_id=user_id) if joined else 0

    status = "✅ Joined" if joined else "➕ Not joined"
    auto_mode = "🔥 Non-stop ON" if (joined and autoq == 1) else "⏸ Paused/Off"

    # runtime status (queue/duel/solo) for clarity
    try:
        from .solo import solo_sessions

        in_solo = user_id in solo_sessions
    except Exception:
        in_solo = False
    in_duel = user_id in state.user_to_duel
    in_queue = bool(state.global_event and user_id in state.global_event.queue)
    if in_solo:
        runtime_status = "🧪 Solo mode"
    elif in_duel:
        runtime_status = "⚔️ In duel"
    elif in_queue:
        runtime_status = "🔎 Searching"
    elif joined and autoq == 1:
        runtime_status = "✅ Ready (auto)"
    else:
        runtime_status = "⏸ Idle"

    lines += [
        f"⏳ Event time left: <b>{mins}m {secs}s</b>",
        f"🧩 Current mode: <b>{html.escape(current_task_type())}</b>",
        "",
        f"👤 You: <b>{html.escape(display_name(user_id))}</b>",
        f"📍 Status: <b>{status}</b>",
        f"⚙️ Mode: <b>{auto_mode}</b>",
        f"🎛 Live: <b>{html.escape(runtime_status)}</b>",
        "",
        "Buttons:",
        "• 🎮 Join & Play — join + auto matchmaking",
        "• ⏸ Pause / ▶️ Resume — control nonstop",
        "• 🏆 Leaderboard — standings",
        "• 📊 My stats — your numbers",
        "• 🧪 Solo test — single-player questions",
    ]
    await context.bot.send_message(
        chat_id=chat_id,
        text="\n".join(lines),
        parse_mode="HTML",
        reply_markup=reply_kb_main(),
    )


