from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
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
    tma_url = get_tma_url()
    play_btn = (
        KeyboardButton("🎮 Play (Mini App)", web_app=WebAppInfo(url=tma_url))
        if tma_url
        else KeyboardButton("🎮 Play (Mini App)")
    )
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


