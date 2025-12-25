from telegram import BotCommand
from telegram.ext import Application

from . import runtime


async def post_init(app: Application) -> None:
    me = await app.bot.get_me()
    runtime.BOT_USERNAME = me.username

    await app.bot.set_my_commands(
        [
            BotCommand("play", "🎮 Open the Mini App game"),
            BotCommand("menu", "📌 Open menu / dashboard"),
            BotCommand("join", "🎮 Join event + nonstop matchmaking"),
            BotCommand("leave", "🚪 Leave queue / stop matchmaking"),
            BotCommand("pause", "⏸ Pause nonstop matchmaking"),
            BotCommand("resume", "▶️ Resume nonstop matchmaking"),
            BotCommand("leaderboard", "🏆 View leaderboard"),
            BotCommand("mystats", "📊 View my stats"),
            BotCommand("help", "ℹ️ Help"),
            BotCommand("solo", "🧪 Solo mode (test questions)"),
            BotCommand("solo_stop", "🛑 Stop solo mode"),
            BotCommand("admin_help", "🛠 (admin) Admin cheat sheet"),
            BotCommand("tma_admin", "🛠 (admin) Get Mini App admin link"),
            BotCommand("tma_set", "🛠 (admin) Set Mini App URL (tunnel)"),
            BotCommand("tma_clear", "🛠 (admin) Clear Mini App URL override"),
            BotCommand("event_start", "✅ (admin) Start event"),
            BotCommand("event_stop", "🛑 (admin) Stop event"),
            BotCommand("importwords", "📥 (admin) Import words"),
            BotCommand("addword", "➕ (admin) Add a word"),
            BotCommand("words_count", "🔢 (admin) Words in DB"),
            BotCommand("vocab_reset", "🧨 (admin) Wipe vocab table"),
        ]
    )


