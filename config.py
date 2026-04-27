"""
config.py - تنظیمات ربات ssh-bot-Robexia

این فایل توسط install.sh ساخته می‌شود.
دستی ویرایش نکنید مگر اینکه بدانید چه می‌کنید.
"""
import os

TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip().isdigit()]

BOT_NAME = "ssh-bot-Robexia"
BOT_USERNAME = ""

# مسیرها
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "bot.db")
LOG_FILE = os.path.join(DATA_DIR, "bot.log")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
STATS_FILE = os.path.join(DATA_DIR, "stats.json")

# ساخت پوشه data اگر نبود
os.makedirs(DATA_DIR, exist_ok=True)
