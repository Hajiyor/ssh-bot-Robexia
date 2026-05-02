"""
handlers/stats.py - ثبت پیام‌ها و ذخیره اطلاعات کاربران
"""

import time
import logging
from database import db

logger = logging.getLogger(__name__)

_msg_history: list = []


def track_message() -> None:
    """ثبت یک پیام در تاریخچه"""
    _msg_history.append(time.time())


async def save_user_and_track(update) -> None:
    """ذخیره/آپدیت کاربر + ثبت پیام"""
    user = update.effective_user
    if user:
        try:
            await db.save_user(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
            )
        except Exception as e:
            logger.warning(f"Save user error: {e}")
    track_message()
