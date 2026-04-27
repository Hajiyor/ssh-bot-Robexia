"""keyboard های داینامیک ترمینال"""

from typing import Optional
from telegram import ReplyKeyboardMarkup, KeyboardButton

# shortcut هایی که باید buffer جدید بسازند (دستور با خروجی)
BUFFERED_SHORTCUTS = {
    "📂 ls -la", "📍 pwd", "🏠 cd ~", "🧹 clear",
    "⬆ آخرین دستور",
}

TERMINAL_NORMAL = ReplyKeyboardMarkup([
    [KeyboardButton("⛔ Ctrl+C"), KeyboardButton("🚪 Ctrl+D"), KeyboardButton("⏸ Ctrl+Z")],
    [KeyboardButton("↹ Tab"), KeyboardButton("⬆ آخرین دستور"), KeyboardButton("🧹 clear")],
    [KeyboardButton("📂 ls -la"), KeyboardButton("📍 pwd"), KeyboardButton("🏠 cd ~")],
    [KeyboardButton("⏸ /wait"), KeyboardButton("❌ /close")],
], resize_keyboard=True, is_persistent=True)

TERMINAL_NANO = ReplyKeyboardMarkup([
    [KeyboardButton("💾 Ctrl+O (ذخیره)"), KeyboardButton("🚪 Ctrl+X (خروج)")],
    [KeyboardButton("🔍 Ctrl+W (جستجو)"), KeyboardButton("🔄 Ctrl+\\ (جایگزینی)")],
    [KeyboardButton("✂️ Ctrl+K (برش خط)"), KeyboardButton("📋 Ctrl+U (paste)")],
    [KeyboardButton("⬆ Ctrl+Y (صفحه بالا)"), KeyboardButton("⬇ Ctrl+V (صفحه پایین)")],
    [KeyboardButton("❓ Ctrl+G (راهنما)"), KeyboardButton("⛔ Ctrl+C (لغو)")],
], resize_keyboard=True, is_persistent=True)

TERMINAL_VIM = ReplyKeyboardMarkup([
    [KeyboardButton("✏️ i (insert)"), KeyboardButton("⌨️ Esc (normal)")],
    [KeyboardButton("💾 :w (ذخیره)"), KeyboardButton("🚪 :q! (خروج)"), KeyboardButton("💾🚪 :wq")],
    [KeyboardButton("⬆ k"), KeyboardButton("⬇ j"), KeyboardButton("⬅ h"), KeyboardButton("➡ l")],
    [KeyboardButton("✂️ dd (حذف خط)"), KeyboardButton("📋 p (paste)"), KeyboardButton("↩ u (undo)")],
    [KeyboardButton("🔍 /"), KeyboardButton("🔄 n (بعدی)"), KeyboardButton("⛔ Ctrl+C")],
], resize_keyboard=True, is_persistent=True)

SFTP_MENU = ReplyKeyboardMarkup([
    [KeyboardButton("🔄 بروزرسانی"), KeyboardButton("⬆️ پوشه بالاتر")],
    [KeyboardButton("📁 تغییر مسیر"), KeyboardButton("🏠 برگشت به home")],
    [KeyboardButton("➕ ساخت پوشه"), KeyboardButton("📄 ساخت فایل")],
    [KeyboardButton("🗑 حذف"), KeyboardButton("✂️ انتقال/تغییر نام")],
    [KeyboardButton("📤 آپلود فایل"), KeyboardButton("📥 دانلود فایل")],
    [KeyboardButton("❌ بستن SFTP")],
], resize_keyboard=True, is_persistent=True)


def detect_terminal_mode(output: str) -> str:
    if not output:
        return 'normal'
    lower = output.lower()
    if any(['gnu nano' in lower, '[ new file ]' in lower]):
        return 'nano'
    if any(['-- insert --' in lower, '-- normal --' in lower,
            '-- visual --' in lower, '-- replace --' in lower]):
        return 'vim'
    return 'normal'


def get_keyboard_for_mode(mode: str) -> ReplyKeyboardMarkup:
    return {'nano': TERMINAL_NANO, 'vim': TERMINAL_VIM}.get(mode, TERMINAL_NORMAL)


# نقشه دکمه → stdin
SHORTCUT_MAP = {
    "⛔ Ctrl+C": "\x03", "🚪 Ctrl+D": "\x04", "⏸ Ctrl+Z": "\x1a",
    "↹ Tab": "\t", "⬆ آخرین دستور": "\x1b[A",
    # nano
    "💾 Ctrl+O (ذخیره)": "\x0f", "🚪 Ctrl+X (خروج)": "\x18",
    "🔍 Ctrl+W (جستجو)": "\x17", "🔄 Ctrl+\\ (جایگزینی)": "\x1c",
    "✂️ Ctrl+K (برش خط)": "\x0b", "📋 Ctrl+U (paste)": "\x15",
    "⬆ Ctrl+Y (صفحه بالا)": "\x19", "⬇ Ctrl+V (صفحه پایین)": "\x16",
    "❓ Ctrl+G (راهنما)": "\x07", "⛔ Ctrl+C (لغو)": "\x03",
    # vim
    "✏️ i (insert)": "i", "⌨️ Esc (normal)": "\x1b",
    "💾 :w (ذخیره)": ":w\n", "🚪 :q! (خروج)": ":q!\n", "💾🚪 :wq": ":wq\n",
    "⬆ k": "k", "⬇ j": "j", "⬅ h": "h", "➡ l": "l",
    "✂️ dd (حذف خط)": "dd", "📋 p (paste)": "p", "↩ u (undo)": "u",
    "🔍 /": "/", "🔄 n (بعدی)": "n",
}

# دستوراتی که buffer جدید می‌سازند
COMMAND_MAP = {
    "🧹 clear": "clear",
    "📂 ls -la": "ls -la",
    "📍 pwd": "pwd",
    "🏠 cd ~": "cd ~",
}


def is_shortcut(text: str) -> bool:
    return text in SHORTCUT_MAP or text in COMMAND_MAP


def get_shortcut_data(text: str) -> tuple:
    """برمی‌گرداند (data, needs_buffer)"""
    if text in COMMAND_MAP:
        return COMMAND_MAP[text], True  # نیاز به buffer جدید
    if text in SHORTCUT_MAP:
        return SHORTCUT_MAP[text], False  # raw بدون buffer
    return None, False


def is_terminal_control(text: str) -> bool:
    return text in ("⏸ /wait", "❌ /close")
