from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .commands import post_init
from .config import BOT_TOKEN, log
from .duel import on_callback
from .handlers import admin as admin_handlers
from .handlers import player as player_handlers
from .solo import cmd_solo, cmd_solo_stop


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Keep it simple: log server-side, and if we can, notify user.
    log.exception("Unhandled error while processing update", exc_info=context.error)
    try:
        if isinstance(update, Update) and update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="⚠️ Something went wrong. Try /menu again.",
            )
    except Exception:
        pass


def build_app() -> Application:
    if not BOT_TOKEN:
        raise SystemExit("Missing BOT_TOKEN env var (put it in .env).")

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_error_handler(_on_error)

    # player commands
    app.add_handler(CommandHandler("start", player_handlers.cmd_start))
    app.add_handler(CommandHandler("play", player_handlers.cmd_play))
    app.add_handler(CommandHandler("menu", player_handlers.cmd_menu))
    app.add_handler(CommandHandler("help", player_handlers.cmd_help))
    app.add_handler(CommandHandler("join", player_handlers.cmd_join))
    app.add_handler(CommandHandler("leave", player_handlers.cmd_leave))
    app.add_handler(CommandHandler("pause", player_handlers.cmd_pause))
    app.add_handler(CommandHandler("resume", player_handlers.cmd_resume))
    app.add_handler(CommandHandler("leaderboard", player_handlers.cmd_leaderboard))
    app.add_handler(CommandHandler("mystats", player_handlers.cmd_mystats))
    app.add_handler(CommandHandler("solo", cmd_solo))
    app.add_handler(CommandHandler("solo_stop", cmd_solo_stop))

    # admin commands
    app.add_handler(CommandHandler("admin_help", admin_handlers.cmd_admin_help))
    app.add_handler(CommandHandler("tma_admin", admin_handlers.cmd_tma_admin))
    app.add_handler(CommandHandler("tma_set", admin_handlers.cmd_tma_set))
    app.add_handler(CommandHandler("tma_clear", admin_handlers.cmd_tma_clear))
    app.add_handler(CommandHandler("event_start", admin_handlers.cmd_event_start))
    app.add_handler(CommandHandler("event_stop", admin_handlers.cmd_event_stop))
    app.add_handler(CommandHandler("addword", admin_handlers.cmd_addword))
    app.add_handler(CommandHandler("importwords", admin_handlers.cmd_importwords))
    app.add_handler(CommandHandler("words_count", admin_handlers.cmd_words_count))
    app.add_handler(CommandHandler("vocab_reset", admin_handlers.cmd_vocab_reset))

    # inline answer buttons
    app.add_handler(CallbackQueryHandler(on_callback))

    # reply-keyboard button text
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, player_handlers.on_text_button)
    )

    return app


def main() -> None:
    app = build_app()
    log.info("Starting bot…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


