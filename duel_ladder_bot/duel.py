import asyncio
import html
import time
from typing import Tuple

from telegram import Update
from telegram.ext import ContextTypes

from . import state
from .config import (
    DEFAULT_ROUNDS_PER_DUEL,
    DEFAULT_ROUND_SECONDS,
    GLOBAL_CHAT_ID,
    PRE_DUEL_COUNTDOWN_SECONDS,
    REST_BETWEEN_DUELS_SECONDS,
    TASK_TYPES,
)
from .helpers import (
    build_post_duel_summary,
    countdown_edit_message,
    current_task_type,
    display_name,
    safe_answer_cbq,
    score_points,
)
from .keyboards import kb_options, reply_kb_main
from .runtime import db


# ----------------------------
# Matchmaking (non-stop)
# ----------------------------
async def maybe_enqueue_and_match(uid: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    ev = db.get_active_event(chat_id=GLOBAL_CHAT_ID)
    if not ev:
        return
    event_id = int(ev["id"])

    if not db.get_player_stats(event_id=event_id, user_id=uid):
        return
    if db.get_auto_queue(event_id=event_id, user_id=uid) != 1:
        return
    if uid in state.user_to_duel:
        return

    if not state.global_event:
        state.global_event = state.GlobalEventState(
            event_id=event_id,
            ends_at=int(ev["ends_at"]),
            phase_seconds=int(ev["phase_seconds"]),
        )

    if uid not in state.global_event.queue:
        state.global_event.queue.append(uid)
        await context.bot.send_message(
            chat_id=uid, text="🔎 Searching for an opponent…", reply_markup=reply_kb_main()
        )

    await try_matchmake(context)


async def try_matchmake(context: ContextTypes.DEFAULT_TYPE) -> None:
    ev = db.get_active_event(chat_id=GLOBAL_CHAT_ID)
    if not ev:
        return
    event_id = int(ev["id"])

    if not state.global_event:
        return

    while len(state.global_event.queue) >= 2:
        p1 = state.global_event.queue.pop(0)
        p2 = None
        for i, cand in enumerate(state.global_event.queue):
            if cand != p1:
                p2 = cand
                state.global_event.queue.pop(i)
                break

        if p2 is None:
            state.global_event.queue.insert(0, p1)
            return

        if p1 in state.user_to_duel or p2 in state.user_to_duel:
            continue

        duel_id = state.next_duel_id()
        duel = state.DuelState(
            duel_id=duel_id,
            event_id=event_id,
            p1_id=p1,
            p2_id=p2,
            task_type=current_task_type(),
            rounds_total=DEFAULT_ROUNDS_PER_DUEL,
            round_seconds=DEFAULT_ROUND_SECONDS,
        )
        state.active_duels[duel_id] = duel
        state.user_to_duel[p1] = duel_id
        state.user_to_duel[p2] = duel_id

        # Run duel flow asynchronously (so matchmaking can continue)
        context.application.create_task(start_duel_flow(duel_id, context))


async def start_duel_flow(duel_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    duel = state.active_duels.get(duel_id)
    if not duel or duel.is_done:
        return

    intro = (
        "⚔️ <b>Duel found!</b>\n\n"
        f"👥 <b>{html.escape(display_name(duel.p1_id))}</b> vs <b>{html.escape(display_name(duel.p2_id))}</b>\n"
        f"🧩 Mode: <b>{html.escape(duel.task_type)}</b>\n"
        f"🔢 Rounds: <b>{duel.rounds_total}</b>\n\n"
        "Rest a bit — starting soon…"
    )
    await context.bot.send_message(
        chat_id=duel.p1_id,
        text=intro,
        parse_mode="HTML",
        reply_markup=reply_kb_main(),
    )
    await context.bot.send_message(
        chat_id=duel.p2_id,
        text=intro,
        parse_mode="HTML",
        reply_markup=reply_kb_main(),
    )

    # Countdown (1 message edited per user)
    await asyncio.gather(
        countdown_edit_message(duel.p1_id, PRE_DUEL_COUNTDOWN_SECONDS, context),
        countdown_edit_message(duel.p2_id, PRE_DUEL_COUNTDOWN_SECONDS, context),
    )

    await run_next_round(duel, context)


# ----------------------------
# Duel engine
# ----------------------------
async def run_next_round(duel: state.DuelState, context: ContextTypes.DEFAULT_TYPE) -> None:
    if duel.is_done:
        return
    if duel.round_idx >= duel.rounds_total:
        await finish_duel(duel, context)
        return

    q = db.build_question(duel.task_type, k_options=4)
    if not q:
        for t in TASK_TYPES:
            q = db.build_question(t, k_options=4)
            if q:
                duel.task_type = t
                break

    if not q:
        msg = "⚠️ Not enough vocabulary in DB to generate questions."
        await context.bot.send_message(chat_id=duel.p1_id, text=msg, reply_markup=reply_kb_main())
        await context.bot.send_message(chat_id=duel.p2_id, text=msg, reply_markup=reply_kb_main())
        await finish_duel(duel, context, force_draw=True)
        return

    duel.active_question = q
    duel.round_started_at = time.time()
    duel.answers = {}
    duel.msg_id_by_user = {}

    def round_header(opp_uid: int) -> str:
        return (
            f"🧠 <b>Round {duel.round_idx + 1}/{duel.rounds_total}</b>\n"
            f"👤 Opponent: <b>{html.escape(display_name(opp_uid))}</b>\n"
            f"⭐ Score: <b>{duel.p1_score} - {duel.p2_score}</b>\n\n"
        )

    kb = kb_options(duel.duel_id, duel.round_idx, q["options"])
    m1 = await context.bot.send_message(
        chat_id=duel.p1_id,
        text=round_header(duel.p2_id) + q["prompt"],
        parse_mode="HTML",
        reply_markup=kb,
    )
    m2 = await context.bot.send_message(
        chat_id=duel.p2_id,
        text=round_header(duel.p1_id) + q["prompt"],
        parse_mode="HTML",
        reply_markup=kb,
    )
    duel.msg_id_by_user[duel.p1_id] = m1.message_id
    duel.msg_id_by_user[duel.p2_id] = m2.message_id

    duel.timer_job = context.job_queue.run_once(
        end_round_job,
        when=duel.round_seconds,
        data={"duel_id": duel.duel_id, "round_idx": duel.round_idx},
    )


async def end_round_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    duel_id = context.job.data["duel_id"]
    round_idx = context.job.data["round_idx"]
    duel = state.active_duels.get(duel_id)
    if not duel or duel.is_done or duel.round_idx != round_idx:
        return
    await reveal_and_advance(duel, context, timed_out=True)


async def reveal_and_advance(
    duel: state.DuelState, context: ContextTypes.DEFAULT_TYPE, timed_out: bool
) -> None:
    q = duel.active_question
    if not q:
        await finish_duel(duel, context, force_draw=True)
        return

    correct_idx = int(q["correct_idx"])
    correct_text = q["options"][correct_idx]

    def eval_user(uid: int) -> Tuple[str, int, bool]:
        ans = duel.answers.get(uid)
        if not ans:
            return ("No answer", 0, False)
        choice = int(ans["choice"])
        latency_ms = int(ans["latency_ms"])
        ok = choice == correct_idx
        pts = score_points(ok, latency_ms)
        return (f"{'✅ Correct' if ok else '❌ Wrong'} • {latency_ms}ms • +{pts}", pts, ok)

    p1_line, p1_pts, p1_ok = eval_user(duel.p1_id)
    p2_line, p2_pts, p2_ok = eval_user(duel.p2_id)

    db.record_round_result(duel.event_id, duel.p1_id, p1_pts, p1_ok)
    db.record_round_result(duel.event_id, duel.p2_id, p2_pts, p2_ok)

    duel.p1_score += p1_pts
    duel.p2_score += p2_pts

    header = "⏱ Time!" if timed_out else "⚡ Both answered!"
    result = (
        f"{header}\n\n"
        f"✅ Correct answer: <b>{html.escape(str(correct_text))}</b>\n\n"
        f"{html.escape(display_name(duel.p1_id))}: {html.escape(p1_line)}\n"
        f"{html.escape(display_name(duel.p2_id))}: {html.escape(p2_line)}\n\n"
        f"⭐ Score: <b>{duel.p1_score} - {duel.p2_score}</b>"
    )

    for uid in [duel.p1_id, duel.p2_id]:
        msg_id = duel.msg_id_by_user.get(uid)
        if msg_id:
            try:
                await context.bot.edit_message_text(
                    chat_id=uid,
                    message_id=msg_id,
                    text=result,
                    parse_mode="HTML",
                )
            except Exception:
                pass

    duel.round_idx += 1
    duel.active_question = None
    duel.msg_id_by_user = {}
    duel.timer_job = None

    await asyncio.sleep(0.7)
    await run_next_round(duel, context)


async def finish_duel(
    duel: state.DuelState,
    context: ContextTypes.DEFAULT_TYPE,
    force_draw: bool = False,
) -> None:
    duel.is_done = True

    winner = None
    loser = None
    if not force_draw:
        if duel.p1_score > duel.p2_score:
            winner, loser = duel.p1_id, duel.p2_id
        elif duel.p2_score > duel.p1_score:
            winner, loser = duel.p2_id, duel.p1_id

    if winner is not None and loser is not None:
        db.record_duel_win_loss(duel.event_id, winner_id=winner, loser_id=loser)

    if winner is None:
        outcome = "🤝 <b>Draw!</b>"
    else:
        outcome = f"🏅 Winner: <b>{html.escape(display_name(winner))}</b>"

    text = (
        "🏁 <b>Duel finished</b>\n\n"
        f"👥 {html.escape(display_name(duel.p1_id))} vs {html.escape(display_name(duel.p2_id))}\n"
        f"⭐ Final score: <b>{duel.p1_score} - {duel.p2_score}</b>\n"
        f"{outcome}\n"
    )

    await context.bot.send_message(
        chat_id=duel.p1_id, text=text, parse_mode="HTML", reply_markup=reply_kb_main()
    )
    await context.bot.send_message(
        chat_id=duel.p2_id, text=text, parse_mode="HTML", reply_markup=reply_kb_main()
    )

    # Post-duel mini leaderboard recap
    summary_p1 = build_post_duel_summary(duel.event_id, duel.p1_id)
    summary_p2 = build_post_duel_summary(duel.event_id, duel.p2_id)
    await context.bot.send_message(
        chat_id=duel.p1_id, text=summary_p1, parse_mode="HTML", reply_markup=reply_kb_main()
    )
    await context.bot.send_message(
        chat_id=duel.p2_id, text=summary_p2, parse_mode="HTML", reply_markup=reply_kb_main()
    )

    state.active_duels.pop(duel.duel_id, None)
    state.user_to_duel.pop(duel.p1_id, None)
    state.user_to_duel.pop(duel.p2_id, None)

    # Rest between battles (non-stop pacing)
    await asyncio.sleep(REST_BETWEEN_DUELS_SECONDS)

    # Auto-continue (non-stop)
    await maybe_enqueue_and_match(duel.p1_id, context)
    await maybe_enqueue_and_match(duel.p2_id, context)


# ----------------------------
# Inline button answers
# ----------------------------
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from .helpers import cache_user

    await cache_user(update)
    await safe_answer_cbq(update)

    q = update.callback_query
    if not q or not q.data:
        return
    parts = q.data.split("|")
    if parts[0] == "solo" and len(parts) == 4:
        from .solo import handle_solo_callback

        await handle_solo_callback(update, context, parts)
        return
    if parts[0] != "ans" or len(parts) != 4:
        return

    uid = update.effective_user.id
    duel_id = int(parts[1])
    round_idx = int(parts[2])
    choice_idx = int(parts[3])

    duel = state.active_duels.get(duel_id)
    if not duel or duel.is_done:
        return
    if uid not in (duel.p1_id, duel.p2_id):
        return
    if duel.round_idx != round_idx:
        return
    if uid in duel.answers:
        return

    latency_ms = int((time.time() - duel.round_started_at) * 1000)
    duel.answers[uid] = {"choice": choice_idx, "latency_ms": latency_ms}

    if duel.p1_id in duel.answers and duel.p2_id in duel.answers:
        try:
            if duel.timer_job:
                duel.timer_job.schedule_removal()
        except Exception:
            pass
        await reveal_and_advance(duel, context, timed_out=False)


