"""کیبوردهای شیشه‌ای (Inline Keyboard)"""

from typing import List, Dict, Any
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def hosts_list_keyboard(hosts: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """لیست سرورها برای my_hosts"""
    buttons = []
    for h in hosts:
        label = f"🖥 {h['name']} ({h['username']}@{h['host']}:{h['port']})"
        buttons.append([InlineKeyboardButton(label, callback_data=f"host_view:{h['id']}")])
    buttons.append([InlineKeyboardButton("➕ افزودن سرور جدید", callback_data="host_add")])
    return InlineKeyboardMarkup(buttons)


def host_actions_keyboard(host_id: int) -> InlineKeyboardMarkup:
    """دکمه‌های عملیات روی یک سرور خاص"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🖥 SSH", callback_data=f"host_connect:{host_id}:ssh"),
            InlineKeyboardButton("📂 SFTP", callback_data=f"host_connect:{host_id}:sftp"),
        ],
        [
            InlineKeyboardButton("✏️ ویرایش", callback_data=f"host_edit:{host_id}"),
            InlineKeyboardButton("🗑 حذف", callback_data=f"host_delete:{host_id}"),
        ],
        [InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="host_list")],
    ])


def confirm_delete_keyboard(host_id: int) -> InlineKeyboardMarkup:
    """تأیید حذف سرور"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ بله، حذف کن", callback_data=f"host_delete_confirm:{host_id}"),
            InlineKeyboardButton("❌ انصراف", callback_data=f"host_view:{host_id}"),
        ],
    ])


def edit_field_keyboard(host_id: int) -> InlineKeyboardMarkup:
    """انتخاب فیلد برای ویرایش"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📛 نام", callback_data=f"edit_field:{host_id}:name"),
            InlineKeyboardButton("🌐 آدرس", callback_data=f"edit_field:{host_id}:host"),
        ],
        [
            InlineKeyboardButton("🔢 پورت", callback_data=f"edit_field:{host_id}:port"),
            InlineKeyboardButton("👤 یوزر", callback_data=f"edit_field:{host_id}:username"),
        ],
        [InlineKeyboardButton("🔐 احراز هویت", callback_data=f"edit_field:{host_id}:auth")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data=f"host_view:{host_id}")],
    ])


def auth_type_keyboard() -> InlineKeyboardMarkup:
    """انتخاب نوع احراز هویت هنگام افزودن/ویرایش سرور"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 رمز عبور", callback_data="auth_type:password")],
        [InlineKeyboardButton("🗝 کلید SSH", callback_data="auth_type:key")],
    ])


def join_channel_keyboard(channel_username: str) -> InlineKeyboardMarkup:
    """دکمه جوین کانال + دکمه بررسی مجدد"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 عضویت در کانال", url=f"https://t.me/{channel_username.lstrip('@')}")],
        [InlineKeyboardButton("✅ عضو شدم", callback_data="check_join")],
    ])


def empty_hosts_keyboard() -> InlineKeyboardMarkup:
    """وقتی لیست سرورها خالی است"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ افزودن اولین سرور", callback_data="host_add")],
    ])
