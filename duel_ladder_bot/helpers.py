import asyncio
import html
import time

from telegram import Update
from telegram.ext import ContextTypes

from . import state
from .config import TASK_TYPES
from .keyboards import reply_kb_main
from .runtime import db


def require_private(update: Update) -> bool:
    ch = update.effective_chat
    return bool(ch and ch.type == "private")


async def cache_user(update: Update) -> None:
    u = update.effective_user
    c = update.effective_chat
    if not u or not c:
        return
    db.upsert_user(
        user_id=u.id,
        username=u.username or "",
        full_name=u.full_name or "",
        last_chat_id=c.id,
    )


def display_name(user_id: int) -> str:
    row = db.get_user(user_id)
    if not row:
        return f"User {user_id}"
    username = (row["username"] or "").strip()
    full_name = (row["full_name"] or "").strip()
    if full_name and username:
        return f"{full_name} (@{username})"
    if username:
        return f"@{username}"
    if full_name:
        return full_name
    return f"User {user_id}"


def current_task_type() -> str:
    if not state.global_event:
        return TASK_TYPES[0]
    return TASK_TYPES[state.global_event.task_idx % len(TASK_TYPES)]


def score_points(is_correct: bool, latency_ms: int) -> int:
    if not is_correct:
        return 0
    if latency_ms <= 2000:
        return 2
    if latency_ms <= 5000:
        return 2
    return 1


async def safe_answer_cbq(update: Update) -> None:
    try:
        if update.callback_query:
            await update.callback_query.answer()
    except Exception:
        pass


async def countdown_edit_message(
    chat_id: int, seconds: int, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Sends 1 message and edits it each second (less spam).
    """
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"🧘 Rest… <b>{seconds}</b> sec\nNext duel starts soon.",
        parse_mode="HTML",
        reply_markup=reply_kb_main(),
    )
    for t in range(seconds - 1, 0, -1):
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg.message_id,
                text=f"🧘 Rest… <b>{t}</b> sec\nNext duel starts soon.",
                parse_mode="HTML",
                reply_markup=reply_kb_main(),
            )
        except Exception:
            pass
        await asyncio.sleep(1)


def build_post_duel_summary(event_id: int, user_id: int) -> str:
    all_rows = db.leaderboard_all(event_id)
    if not all_rows:
        return "🏆 Leaderboard is empty."

    rank = None
    me = None
    for idx, r in enumerate(all_rows, start=1):
        if int(r["user_id"]) == user_id:
            rank = idx
            me = r
            break

    medals = ["🥇", "🥈", "🥉"]
    top3 = all_rows[:3]
    top_lines = []
    for i, r in enumerate(top3):
        top_lines.append(
            f"{medals[i]} {html.escape(display_name(int(r['user_id'])))} — "
            f"W:{r['wins']} • Pts:{r['points']}"
        )

    if me is None:
        return "<b>🏆 Leaderboard</b>\n\n" + "\n".join(top_lines)

    return (
        "<b>🏁 Quick recap</b>\n\n"
        f"📍 Your rank: <b>#{rank}</b>\n"
        f"✅ Your wins: <b>{me['wins']}</b>\n"
        f"⭐ Your points: <b>{me['points']}</b>\n\n"
        "<b>Top 3</b>\n" + "\n".join(top_lines)
    )


