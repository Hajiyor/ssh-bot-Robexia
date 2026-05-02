"""
config.py - ssh-bot-Robexia

تنظیمات از فایل .env خوانده می‌شوند.
این فایل توسط install.sh در زمان نصب ساخته می‌شود.
"""

import os

# ─── توکن و ادمین ─────────────────────────────────────────────────
TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_IDS = [
    int(x) for x in os.environ.get("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
]

# ─── مسیرها ───────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(BASE_DIR, "data")
DB_PATH   = os.path.join(DATA_DIR, "bot.db")
LOG_FILE  = os.path.join(DATA_DIR, "bot.log")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# ─── مشخصات ربات ──────────────────────────────────────────────────
BOT_NAME     = "ssh-bot-Robexia"
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")
VERSION      = "v1.0"

# ساخت پوشه data اگر وجود نداشته باشد
os.makedirs(DATA_DIR, exist_ok=True)
