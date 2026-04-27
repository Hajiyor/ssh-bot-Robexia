"""channel_check.py - بررسی جوین اجباری"""

import json
import os
import logging
from typing import Optional, Tuple
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import TelegramError

logger = logging.getLogger(__name__)
SETTINGS_FILE = "settings.json"


def load_settings() -> dict:
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Settings load error: {e}")
        return {}


def save_settings(data: dict) -> None:
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Settings save error: {e}")


def ensure_default_settings() -> None:
    if not os.path.exists(SETTINGS_FILE):
        save_settings({
            "force_join": {
                "enabled": False,
                "channel_link": "",       # لینک برای نمایش به کاربر
                "channel_username": "",   # @username برای لینک دکمه
                "channel_id": None,       # آیدی عددی برای چک عضویت
            },
            "maintenance": False,
        })


def get_force_join_config() -> dict:
    return load_settings().get("force_join", {"enabled": False})


async def is_user_joined(bot: Bot, user_id: int) -> bool:
    """چک عضویت کاربر در کانال"""
    cfg = get_force_join_config()
    if not cfg.get("enabled"):
        return True

    # برای چک عضویت، channel_id یا username لازم است
    channel = cfg.get("channel_id") or cfg.get("channel_username")
    if not channel:
        logger.warning("Force join enabled but no channel configured!")
        return True

    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except TelegramError as e:
        logger.warning(f"Channel membership check error: {e}")
        # اگر ربات ادمین کانال نیست یا کانال اشتباه است، اجازه می‌دهیم
        return True


def get_join_keyboard() -> Optional[InlineKeyboardMarkup]:
    """کیبورد جوین اجباری با دکمه لینک + بررسی"""
    cfg = get_force_join_config()
    if not cfg.get("enabled"):
        return None

    link = cfg.get("channel_link") or cfg.get("channel_username", "")
    if not link:
        return None

    # اگر username بود، لینک t.me بساز
    if link.startswith("@"):
        url = f"https://t.me/{link.lstrip('@')}"
    elif not link.startswith("http"):
        url = f"https://t.me/{link}"
    else:
        url = link

    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 عضویت در کانال", url=url)],
        [InlineKeyboardButton("✅ عضو شدم، بررسی کن", callback_data="check_join")],
    ])


def get_channel_username() -> str:
    cfg = get_force_join_config()
    return cfg.get("channel_username") or ""
