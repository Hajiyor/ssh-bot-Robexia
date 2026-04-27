"""کیبوردهای اصلی ربات"""

from telegram import ReplyKeyboardMarkup, KeyboardButton

MAIN_MENU = ReplyKeyboardMarkup(
    [
        [KeyboardButton("⚡ اتصال سریع"), KeyboardButton("📋 سرورهای من")],
        [KeyboardButton("❓ راهنما")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

CANCEL_MENU = ReplyKeyboardMarkup(
    [[KeyboardButton("🚫 لغو")]],
    resize_keyboard=True,
    one_time_keyboard=True,
)


def is_main_menu_button(text: str) -> bool:
    return text in ("⚡ اتصال سریع", "📋 سرورهای من", "❓ راهنما")
