import html
import time
from dataclasses import dataclass
from typing import Any, Optional

from telegram import Update
from telegram.ext import ContextTypes

from .config import DEFAULT_ROUNDS_PER_DUEL, DEFAULT_ROUND_SECONDS, GLOBAL_CHAT_ID, TASK_TYPES
from .helpers import cache_user, current_task_type, require_private, score_points
from .keyboards import kb_options, reply_kb_main
from .runtime import db


@dataclass
class SoloSession:
    session_id: int
    user_id: int
    event_id: Optional[int]  # if present, record stats into this event
    task_type: str
    rounds_total: int
    round_seconds: int
    round_idx: int = 0
    score: int = 0
    active_question: Optional[dict] = None
    round_started_at: float = 0.0
    msg_id: Optional[int] = None
    timer_job: Any = None


solo_sessions: dict[int, SoloSession] = {}
_solo_seq = 9000


def _next_session_id() -> int:
    global _solo_seq
    _solo_seq += 1
    return _solo_seq


def _split_list(s: str) -> list[str]:
    s = (s or "").strip()
    if not s:
        return []
    # common separators in your doc exports: ';' and ',' and '•'
    s = s.replace("•", ";")
    parts: list[str] = []
    for chunk in s.split(";"):
        for p in chunk.split(","):
            p = p.strip()
            if p:
                parts.append(p)
    # de-dupe preserving order
    out: list[str] = []
    for p in parts:
        if p not in out:
            out.append(p)
    return out


async def cmd_solo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cache_user(update)
    if not require_private(update):
        return
    uid = update.effective_user.id

    # If there's an active global event and the user is joined, we record stats there.
    ev = db.get_active_event(chat_id=GLOBAL_CHAT_ID)
    event_id: Optional[int] = None
    if ev:
        eid = int(ev["id"])
        if db.get_player_stats(event_id=eid, user_id=uid):
            event_id = eid
            # pause auto-queue while soloing
            db.set_auto_queue(event_id=eid, user_id=uid, auto_queue=0)

    # Stop existing solo session (if any) and start fresh
    await stop_solo(uid, context)

    sess = SoloSession(
        session_id=_next_session_id(),
        user_id=uid,
        event_id=event_id,
        task_type=current_task_type() if ev else TASK_TYPES[0],
        rounds_total=DEFAULT_ROUNDS_PER_DUEL,
        round_seconds=DEFAULT_ROUND_SECONDS,
    )
    solo_sessions[uid] = sess

    note = (
        "🧪 <b>Solo mode</b> started.\n"
        "This runs MCQs for a single player (great for testing).\n\n"
        f"🧩 Mode: <b>{html.escape(sess.task_type)}</b>\n"
        f"🔢 Rounds: <b>{sess.rounds_total}</b>\n"
    )
    if sess.event_id is None:
        note += "\n<i>Note: no active event stats will be recorded.</i>"
    else:
        note += "\n<i>Note: points/correct/wrong will be recorded into the active event.</i>"

    await update.effective_message.reply_text(note, parse_mode="HTML", reply_markup=reply_kb_main())
    await _run_next_solo_round(sess, context)


async def cmd_solo_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cache_user(update)
    if not require_private(update):
        return
    uid = update.effective_user.id
    stopped = await stop_solo(uid, context)
    if stopped:
        await update.effective_message.reply_text("🛑 Solo mode stopped.", reply_markup=reply_kb_main())
    else:
        await update.effective_message.reply_text("No active solo session.", reply_markup=reply_kb_main())


async def stop_solo(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    sess = solo_sessions.pop(user_id, None)
    if not sess:
        return False
    try:
        if sess.timer_job:
            sess.timer_job.schedule_removal()
    except Exception:
        pass
    return True


async def _run_next_solo_round(sess: SoloSession, context: ContextTypes.DEFAULT_TYPE) -> None:
    if sess.round_idx >= sess.rounds_total:
        await _finish_solo(sess, context)
        return

    q = db.build_question(sess.task_type, k_options=4)
    if not q:
        # fall back to any available task type
        for t in TASK_TYPES:
            q = db.build_question(t, k_options=4)
            if q:
                sess.task_type = t
                break

    if not q:
        await context.bot.send_message(
            chat_id=sess.user_id,
            text="⚠️ Not enough vocabulary in DB to generate questions.",
            reply_markup=reply_kb_main(),
        )
        await _finish_solo(sess, context)
        return

    sess.active_question = q
    sess.round_started_at = time.time()

    kb = kb_options(sess.session_id, sess.round_idx, q["options"], prefix="solo")
    text = (
        f"🧪 <b>Solo Round {sess.round_idx + 1}/{sess.rounds_total}</b>\n"
        f"🧩 Mode: <b>{html.escape(sess.task_type)}</b>\n"
        f"⭐ Score: <b>{sess.score}</b>\n\n"
        + q["prompt"]
    )
    msg = await context.bot.send_message(
        chat_id=sess.user_id,
        text=text,
        parse_mode="HTML",
        reply_markup=kb,
    )
    sess.msg_id = msg.message_id

    sess.timer_job = context.job_queue.run_once(
        _solo_timeout_job,
        when=sess.round_seconds,
        data={"user_id": sess.user_id, "session_id": sess.session_id, "round_idx": sess.round_idx},
    )


async def _solo_timeout_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data
    uid = int(data["user_id"])
    session_id = int(data["session_id"])
    round_idx = int(data["round_idx"])
    sess = solo_sessions.get(uid)
    if not sess or sess.session_id != session_id or sess.round_idx != round_idx:
        return
    await _reveal_solo(sess, context, choice_idx=None, timed_out=True)


async def handle_solo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    """
    callback_data format: solo|<session_id>|<round_idx>|<choice_idx>
    """
    await cache_user(update)

    q = update.callback_query
    if not q or not q.data:
        return

    uid = update.effective_user.id
    if uid not in solo_sessions:
        return

    sess = solo_sessions[uid]
    session_id = int(parts[1])
    round_idx = int(parts[2])
    choice_idx = int(parts[3])

    if sess.session_id != session_id or sess.round_idx != round_idx:
        return

    # stop timer
    try:
        if sess.timer_job:
            sess.timer_job.schedule_removal()
    except Exception:
        pass
    sess.timer_job = None

    await _reveal_solo(sess, context, choice_idx=choice_idx, timed_out=False)


async def _reveal_solo(
    sess: SoloSession,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    choice_idx: Optional[int],
    timed_out: bool,
) -> None:
    q = sess.active_question
    if not q:
        await _finish_solo(sess, context)
        return

    correct_idx = int(q["correct_idx"])
    correct_text = q["options"][correct_idx]

    if choice_idx is None:
        latency_ms = int(sess.round_seconds * 1000)
        ok = False
        pts = 0
        verdict = "⏱ Time!"
        pick = "No answer"
    else:
        latency_ms = int((time.time() - sess.round_started_at) * 1000)
        ok = int(choice_idx) == correct_idx
        pts = score_points(ok, latency_ms)
        verdict = "✅ Correct!" if ok else "❌ Wrong!"
        pick = q["options"][int(choice_idx)]

    sess.score += pts

    # optionally record into event stats
    if sess.event_id is not None:
        db.record_round_result(sess.event_id, sess.user_id, pts, ok)

    result = (
        f"{verdict}\n\n"
        f"✅ Correct answer: <b>{html.escape(str(correct_text))}</b>\n"
        f"👉 Your pick: <b>{html.escape(str(pick))}</b>\n"
        f"⏱ {latency_ms}ms • +{pts}\n\n"
        f"⭐ Score: <b>{sess.score}</b>"
    )

    if sess.msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=sess.user_id,
                message_id=sess.msg_id,
                text=result,
                parse_mode="HTML",
                reply_markup=None,
            )
        except Exception:
            await context.bot.send_message(
                chat_id=sess.user_id, text=result, parse_mode="HTML", reply_markup=reply_kb_main()
            )

    sess.round_idx += 1
    sess.active_question = None
    sess.msg_id = None

    await _run_next_solo_round(sess, context)


async def _finish_solo(sess: SoloSession, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = sess.user_id
    solo_sessions.pop(uid, None)
    text = (
        "🏁 <b>Solo mode finished</b>\n\n"
        f"⭐ Final score: <b>{sess.score}</b>\n\n"
        "Run /solo to start again, or /menu to go back."
    )
    await context.bot.send_message(chat_id=uid, text=text, parse_mode="HTML", reply_markup=reply_kb_main())


