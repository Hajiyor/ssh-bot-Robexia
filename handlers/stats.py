"""
stats.py - Message tracking and stats reporter
Compatible with standalone deployment (no Hpanel required)
"""

import asyncio
import json
import time
import logging
from datetime import datetime

import httpx
import config
from database import db

logger = logging.getLogger(__name__)
_msg_history: list = []


def track_message() -> None:
    _msg_history.append(time.time())


async def _ping_telegram() -> float:
    try:
        start = time.time()
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"https://api.telegram.org/bot{config.TOKEN}/getMe")
            if r.status_code == 200:
                return round((time.time() - start) * 1000, 1)
    except Exception:
        pass
    return 0.0


async def stats_reporter() -> None:
    global _msg_history
    while True:
        try:
            now = time.time()
            _msg_history = [t for t in _msg_history if now - t < 3600]
            stats = {
                "messages_per_min": sum(1 for t in _msg_history if now - t < 60),
                "messages_per_hour": len(_msg_history),
                "ping_ms": await _ping_telegram(),
                "last_update": datetime.utcnow().isoformat() + "Z",
            }
            try:
                with open(config.STATS_FILE, "w", encoding="utf-8") as f:
                    json.dump(stats, f)
            except Exception as e:
                logger.warning(f"Stats write error: {e}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.exception(f"Stats reporter error: {e}")
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            break


async def save_user_and_track(update) -> None:
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
