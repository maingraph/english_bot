import html
import time
from typing import Tuple

from telegram import Update
from telegram.ext import ContextTypes

from .. import state
from ..config import (
    ADMIN_TOKEN,
    DEFAULT_PHASE_SECONDS,
    GLOBAL_CHAT_ID,
    PRE_DUEL_COUNTDOWN_SECONDS,
    REST_BETWEEN_DUELS_SECONDS,
    TASK_TYPES,
    is_admin,
)
from ..helpers import cache_user, current_task_type, require_private
from ..keyboards import reply_kb_main
from ..runtime import BOT_USERNAME, db, get_tma_url, set_tma_url


async def cmd_admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cache_user(update)
    if not require_private(update):
        return
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Admins only.")
        return

    text = (
        "<b>🛠 Admin cheat sheet</b>\n\n"
        "Event:\n"
        "• /event_start &lt;minutes&gt; [phase_seconds]\n"
        "• /event_stop\n\n"
        "Mini App:\n"
        "• /tma_admin  (get admin Mini App link)\n\n"
        "• /tma_set &lt;https-url&gt;  (set tunnel URL without restart)\n"
        "• /tma_clear  (clear tunnel URL override)\n\n"
        "Vocabulary:\n"
        "• /words_count\n"
        "• /addword word|definition|translation|syn1,syn2|ant1,ant2|example\n"
        "• /importwords  (then paste many lines below)\n"
        "• /vocab_reset CONFIRM  (wipes only the vocab table)\n\n"
        "Tip:\n"
        "• Check /words_count before /event_start."
    )
    await update.effective_message.reply_text(
        text, parse_mode="HTML", reply_markup=reply_kb_main()
    )


async def cmd_tma_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cache_user(update)
    if not require_private(update):
        return
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Admins only.")
        return
    tma_url = get_tma_url()
    if not tma_url:
        await update.effective_message.reply_text(
            "TMA_URL is not configured. Set env var TMA_URL and restart."
        )
        return
    await update.effective_message.reply_text(
        "🛠 Mini App admin link (keep this private):\n"
        f"{tma_url}/?admin={ADMIN_TOKEN}",
        reply_markup=reply_kb_main(),
    )


async def cmd_tma_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cache_user(update)
    if not require_private(update):
        return
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Admins only.")
        return
    url = (context.args[0].strip() if context.args else "")
    if not (url.startswith("https://") or url.startswith("http://localhost") or url.startswith("http://127.0.0.1")):
        await update.effective_message.reply_text(
            "Usage: /tma_set <https-url>\n\nExample:\n/tma_set https://xxxx.trycloudflare.com"
        )
        return
    set_tma_url(url)
    await update.effective_message.reply_text(
        f"✅ TMA URL set to:\n{get_tma_url()}",
        reply_markup=reply_kb_main(),
    )


async def cmd_tma_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cache_user(update)
    if not require_private(update):
        return
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Admins only.")
        return
    set_tma_url(None)
    await update.effective_message.reply_text(
        "✅ Cleared TMA URL override.", reply_markup=reply_kb_main()
    )


# ---- event admin ----
async def cmd_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cache_user(update)
    if not require_private(update):
        await update.effective_message.reply_text("Start events from a private chat.")
        return
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("Only admins can start events.")
        return
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text(
            "Usage: /event_start <minutes> [phase_seconds]"
        )
        return

    minutes = int(context.args[0])
    phase_seconds = DEFAULT_PHASE_SECONDS
    if len(context.args) >= 2 and context.args[1].isdigit():
        phase_seconds = max(30, int(context.args[1]))

    await stop_event(context)

    eid = db.create_event(minutes=minutes, phase_seconds=phase_seconds, chat_id=GLOBAL_CHAT_ID)
    ends_at = int(time.time()) + minutes * 60

    state.global_event = state.GlobalEventState(
        event_id=eid, ends_at=ends_at, phase_seconds=phase_seconds
    )

    state.global_event.phase_job = context.job_queue.run_repeating(
        rotate_phase_job, interval=phase_seconds, first=phase_seconds, data={"event_id": eid}
    )
    state.global_event.end_job = context.job_queue.run_once(
        end_event_job, when=minutes * 60, data={"event_id": eid}
    )

    link = f"https://t.me/{BOT_USERNAME}" if BOT_USERNAME else "(bot username unknown yet)"
    await update.effective_message.reply_text(
        "✅ <b>Event started!</b>\n\n"
        f"⏱ Duration: <b>{minutes} min</b>\n"
        f"🔁 Mode switches: every <b>{phase_seconds}s</b>\n"
        f"🧩 Current mode: <b>{html.escape(current_task_type())}</b>\n\n"
        "Send this to players:\n"
        f"1) Open the bot: {link}\n"
        "2) Press Start\n"
        "3) Tap 🎮 Join & Play\n",
        parse_mode="HTML",
        reply_markup=reply_kb_main(),
    )


async def cmd_event_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cache_user(update)
    if not require_private(update):
        await update.effective_message.reply_text("Stop events from a private chat.")
        return
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("Only admins can stop events.")
        return
    await stop_event(context)
    await update.effective_message.reply_text("🛑 Event stopped.", reply_markup=reply_kb_main())


async def stop_event(context: ContextTypes.DEFAULT_TYPE) -> None:
    if state.global_event:
        try:
            if state.global_event.phase_job:
                state.global_event.phase_job.schedule_removal()
        except Exception:
            pass
        try:
            if state.global_event.end_job:
                state.global_event.end_job.schedule_removal()
        except Exception:
            pass
        state.global_event.queue.clear()
    db.deactivate_events(chat_id=GLOBAL_CHAT_ID)
    state.global_event = None


async def rotate_phase_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    if not state.global_event:
        return
    state.global_event.task_idx = (state.global_event.task_idx + 1) % len(TASK_TYPES)


async def end_event_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await stop_event(context)


# ---- vocab import ----
def parse_word_line(line: str) -> Tuple[str, str, str, list[str], list[str], str]:
    parts = [p.strip() for p in line.split("|")]
    while len(parts) < 6:
        parts.append("")
    word, definition, translation, syns, ants, example = parts[:6]
    synonyms = [s.strip() for s in syns.split(",")] if syns else []
    antonyms = [a.strip() for a in ants.split(",")] if ants else []
    return word, definition, translation, synonyms, antonyms, example


async def cmd_addword(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cache_user(update)
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("Only admins can add words.")
        return
    raw = update.effective_message.text
    payload = raw.split(" ", 1)[1].strip() if " " in raw else ""
    if not payload:
        await update.effective_message.reply_text(
            "Usage:\n/addword word|definition|translation|syn1,syn2|ant1,ant2|example"
        )
        return
    word, definition, translation, synonyms, antonyms, example = parse_word_line(payload)
    if not word:
        await update.effective_message.reply_text("Word is required.")
        return
    vid = db.add_word(word, definition, translation, synonyms, antonyms, example)
    await update.effective_message.reply_text(
        f"Added vocab id={vid}. Total words: {db.count_words()}"
    )


async def cmd_importwords(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cache_user(update)
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("Only admins can import words.")
        return
    text = update.effective_message.text
    lines = text.splitlines()
    if len(lines) <= 1:
        await update.effective_message.reply_text(
            "Usage:\n/importwords\nword|definition|translation|syn1,syn2|ant1,ant2|example\nword2|..."
        )
        return
    ok = 0
    bad = 0
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        try:
            word, definition, translation, synonyms, antonyms, example = parse_word_line(line)
            if not word:
                bad += 1
                continue
            db.add_word(word, definition, translation, synonyms, antonyms, example)
            ok += 1
        except Exception:
            bad += 1
    await update.effective_message.reply_text(
        f"Imported: {ok}, failed: {bad}. Total words: {db.count_words()}"
    )


async def cmd_words_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cache_user(update)
    await update.effective_message.reply_text(f"Words in DB: {db.count_words()}")


async def cmd_vocab_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Wipes ONLY the `vocab` table (keeps users/events/history).
    """
    await cache_user(update)
    if not require_private(update):
        return
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Admins only.")
        return

    ev = db.get_active_event(chat_id=GLOBAL_CHAT_ID)
    if ev:
        await update.effective_message.reply_text(
            "⛔ Stop the active event first with /event_stop, then run /vocab_reset CONFIRM."
        )
        return

    confirm = (context.args[0].strip().upper() if context.args else "")
    if confirm != "CONFIRM":
        await update.effective_message.reply_text(
            "⚠️ This deletes ALL vocab rows.\n\nRun:\n/vocab_reset CONFIRM"
        )
        return

    before = db.count_words()
    db.wipe_words()
    await update.effective_message.reply_text(
        f"✅ Vocab wiped. Deleted {before} rows. Words in DB now: {db.count_words()}."
    )


