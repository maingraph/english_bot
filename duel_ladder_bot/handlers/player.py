import html

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes

from ..config import GLOBAL_CHAT_ID
from ..dashboard import send_dashboard
from ..helpers import cache_user, display_name, require_private
from ..keyboards import reply_kb_main
from ..runtime import db, get_tma_url
from ..duel import maybe_enqueue_and_match
from ..solo import cmd_solo, cmd_solo_stop


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cache_user(update)
    if not require_private(update):
        await update.effective_message.reply_text("Please open the bot in a private chat 🙂")
        return
    await send_dashboard(update.effective_chat.id, update.effective_user.id, context)


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cache_user(update)
    if not require_private(update):
        await update.effective_message.reply_text("Please open the bot in a private chat 🙂")
        return
    await send_dashboard(update.effective_chat.id, update.effective_user.id, context)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cache_user(update)
    text = (
        "<b>ℹ️ Help</b>\n\n"
        "How to play:\n"
        "1) Host starts an event (/event_start)\n"
        "2) You press 🎮 Join & Play\n"
        "3) The bot matches you into nonstop 1v1 duels\n\n"
        "Commands:\n"
        "/menu\n"
        "/join\n"
        "/leave\n"
        "/pause\n"
        "/resume\n"
        "/solo\n"
        "/solo_stop\n"
        "/leaderboard\n"
        "/mystats\n"
    )
    await update.effective_message.reply_text(
        text, parse_mode="HTML", reply_markup=reply_kb_main()
    )

async def cmd_play(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cache_user(update)
    if not require_private(update):
        return
    tma_url = get_tma_url()
    if not tma_url:
        await update.effective_message.reply_text(
            "Mini App URL is not configured yet. Set env var TMA_URL and restart the bot."
        )
        return
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🎮 Open Game (Mini App)", web_app=WebAppInfo(url=tma_url))]]
    )
    await update.effective_message.reply_text(
        "🎮 <b>Mini App</b>\n\n"
        "Tap the button below to open the game inside Telegram.\n"
        "<i>(Do not open the URL directly — it won’t authenticate.)</i>",
        parse_mode="HTML",
        reply_markup=kb,
    )

async def cmd_leave(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Leaves the matchmaking queue / turns off auto-queue without deleting stats.
    """
    await cache_user(update)
    if not require_private(update):
        await update.effective_message.reply_text("Open the bot in a private chat 🙂")
        return

    ev = db.get_active_event(chat_id=GLOBAL_CHAT_ID)
    if not ev:
        await update.effective_message.reply_text("⛔ No active event.")
        return

    event_id = int(ev["id"])
    uid = update.effective_user.id
    if not db.get_player_stats(event_id=event_id, user_id=uid):
        await update.effective_message.reply_text("You’re not joined. Tap 🎮 Join & Play.")
        return

    db.set_auto_queue(event_id=event_id, user_id=uid, auto_queue=0)
    from .. import state  # local import to avoid cycles

    if state.global_event and uid in state.global_event.queue:
        state.global_event.queue = [u for u in state.global_event.queue if u != uid]

    await update.effective_message.reply_text(
        "🚪 Left the queue. You won’t be auto-matched (use ▶️ Resume to queue again).",
        reply_markup=reply_kb_main(),
    )


async def cmd_join(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cache_user(update)
    if not require_private(update):
        await update.effective_message.reply_text("Open the bot in a private chat 🙂")
        return

    ev = db.get_active_event(chat_id=GLOBAL_CHAT_ID)
    if not ev:
        await update.effective_message.reply_text("⛔ No active event.")
        return

    event_id = int(ev["id"])
    uid = update.effective_user.id

    db.ensure_player(event_id=event_id, user_id=uid, chat_id=GLOBAL_CHAT_ID)
    db.set_auto_queue(event_id=event_id, user_id=uid, auto_queue=1)

    await update.effective_message.reply_text(
        "🎮 <b>Joined!</b>\n" "🔥 Non-stop mode is ON — matchmaking starts now…",
        parse_mode="HTML",
        reply_markup=reply_kb_main(),
    )
    await maybe_enqueue_and_match(uid, context)


async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cache_user(update)
    if not require_private(update):
        await update.effective_message.reply_text("Open the bot in a private chat 🙂")
        return
    ev = db.get_active_event(chat_id=GLOBAL_CHAT_ID)
    if not ev:
        await update.effective_message.reply_text("No active event.")
        return
    event_id = int(ev["id"])
    uid = update.effective_user.id
    if not db.get_player_stats(event_id=event_id, user_id=uid):
        await update.effective_message.reply_text("You are not joined. Tap 🎮 Join & Play.")
        return

    db.set_auto_queue(event_id=event_id, user_id=uid, auto_queue=0)
    from .. import state  # local import to avoid handler import cycles

    if state.global_event and uid in state.global_event.queue:
        state.global_event.queue = [u for u in state.global_event.queue if u != uid]

    await update.effective_message.reply_text(
        "⏸ Paused. You will not be auto-matched.", reply_markup=reply_kb_main()
    )


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cache_user(update)
    if not require_private(update):
        await update.effective_message.reply_text("Open the bot in a private chat 🙂")
        return
    ev = db.get_active_event(chat_id=GLOBAL_CHAT_ID)
    if not ev:
        await update.effective_message.reply_text("No active event.")
        return
    event_id = int(ev["id"])
    uid = update.effective_user.id
    if not db.get_player_stats(event_id=event_id, user_id=uid):
        await update.effective_message.reply_text("Join first: 🎮 Join & Play.")
        return

    db.set_auto_queue(event_id=event_id, user_id=uid, auto_queue=1)
    await update.effective_message.reply_text(
        "▶️ Resumed. Matchmaking starts…", reply_markup=reply_kb_main()
    )
    await maybe_enqueue_and_match(uid, context)


async def cmd_mystats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cache_user(update)
    if not require_private(update):
        await update.effective_message.reply_text("Open the bot in a private chat 🙂")
        return
    ev = db.get_active_event(chat_id=GLOBAL_CHAT_ID)
    if not ev:
        await update.effective_message.reply_text("No active event.")
        return
    event_id = int(ev["id"])
    uid = update.effective_user.id
    row = db.get_player_stats(event_id=event_id, user_id=uid)
    if not row:
        await update.effective_message.reply_text("Not joined. Tap 🎮 Join & Play.")
        return

    autoq = db.get_auto_queue(event_id=event_id, user_id=uid)
    mode = "🔥 Non-stop ON" if autoq == 1 else "⏸ Paused"

    text = (
        "<b>📊 Your stats</b>\n\n"
        f"👤 {html.escape(display_name(uid))}\n"
        f"⚙️ Mode: <b>{mode}</b>\n\n"
        f"✅ Wins: <b>{row['wins']}</b>\n"
        f"❌ Losses: <b>{row['losses']}</b>\n"
        f"⭐ Points: <b>{row['points']}</b>\n"
        f"🎯 Correct: {row['correct']} / Wrong: {row['wrong']}\n"
    )
    await update.effective_message.reply_text(
        text, parse_mode="HTML", reply_markup=reply_kb_main()
    )


async def cmd_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cache_user(update)
    if not require_private(update):
        await update.effective_message.reply_text("Open the bot in a private chat 🙂")
        return

    ev = db.get_active_event(chat_id=GLOBAL_CHAT_ID)
    if not ev:
        await update.effective_message.reply_text("⛔ No active event.")
        return

    event_id = int(ev["id"])
    uid = update.effective_user.id

    all_rows = db.leaderboard_all(event_id)
    if not all_rows:
        await update.effective_message.reply_text("Leaderboard is empty. Join & play!")
        return

    my_rank = None
    my_row = None
    for idx, r in enumerate(all_rows, start=1):
        if int(r["user_id"]) == uid:
            my_rank = idx
            my_row = r
            break

    top = all_rows[:10]
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    lines = ["<b>🏆 Leaderboard</b>", ""]
    for idx, r in enumerate(top, start=1):
        prefix = medals.get(idx, f"{idx}.")
        name = html.escape(display_name(int(r["user_id"])))
        row_txt = (
            f"{prefix} {name}\n   ✅ Wins: <b>{r['wins']}</b>   ⭐ Points: <b>{r['points']}</b>"
        )
        if int(r["user_id"]) == uid:
            row_txt = "👉 " + row_txt + " 👈"
        lines.append(row_txt)
        lines.append("")  # spacing

    if my_rank is None:
        lines += ["You’re not in this event yet. Tap 🎮 Join & Play."]
    else:
        lines += [
            f"📍 Your rank: <b>#{my_rank}</b> | ✅ Wins: <b>{my_row['wins']}</b> | ⭐ Points: <b>{my_row['points']}</b>"
        ]

    await update.effective_message.reply_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=reply_kb_main()
    )


async def on_text_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cache_user(update)
    if not require_private(update):
        return
    txt = (update.effective_message.text or "").strip()

    if txt == "🎮 Join & Play":
        await cmd_join(update, context)
    elif txt == "🎮 Play (Mini App)":
        # Fallback path (only triggers if TMA_URL is not set; otherwise Telegram opens web_app directly).
        await cmd_play(update, context)
    elif txt == "⏸ Pause":
        await cmd_pause(update, context)
    elif txt == "▶️ Resume":
        await cmd_resume(update, context)
    elif txt == "🏆 Leaderboard":
        await cmd_leaderboard(update, context)
    elif txt == "📊 My stats":
        await cmd_mystats(update, context)
    elif txt == "🛠 Admin help":
        from .admin import cmd_admin_help

        await cmd_admin_help(update, context)
    elif txt == "ℹ️ Help":
        await cmd_help(update, context)
    elif txt == "📌 Menu":
        await cmd_menu(update, context)
    elif txt == "🧪 Solo test":
        await cmd_solo(update, context)
    else:
        await update.effective_message.reply_text(
            "Tip: use the buttons 🙂\nTry /menu",
            reply_markup=reply_kb_main(),
        )


