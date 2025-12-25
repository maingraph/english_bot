from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from .runtime import get_tma_url


def kb_options(
    duel_id: int, round_idx: int, options: list[str], *, prefix: str = "ans"
) -> InlineKeyboardMarkup:
    rows = []
    for i, opt in enumerate(options):
        rows.append(
            [
                InlineKeyboardButton(
                    opt[:60], callback_data=f"{prefix}|{duel_id}|{round_idx}|{i}"
                )
            ]
        )
    return InlineKeyboardMarkup(rows)


def reply_kb_main() -> ReplyKeyboardMarkup:
    # Important: don't use ReplyKeyboard "web_app" buttons here.
    # Some Telegram clients open those like a normal browser link, resulting in
    # missing WebApp initData (and "Invalid auth").
    # Instead, users tap this button and the bot replies with an InlineKeyboard
    # WebApp button (handled in handlers/player.py cmd_play).
    play_btn = KeyboardButton("🎮 Play (Mini App)")
    keyboard = [
        [play_btn],
        [KeyboardButton("🎮 Join & Play"), KeyboardButton("⏸ Pause")],
        [KeyboardButton("▶️ Resume"), KeyboardButton("🏆 Leaderboard")],
        [KeyboardButton("📊 My stats"), KeyboardButton("🛠 Admin help")],
        [KeyboardButton("🧪 Solo test"), KeyboardButton("📌 Menu")],
        [KeyboardButton("ℹ️ Help")],
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Tap a button or type /menu …",
    )


