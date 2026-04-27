"""help.py - هندلر /help (متن از DB قابل تغییر است)"""

from telegram import Update
from telegram.ext import ContextTypes
from handlers.stats import save_user_and_track
from keyboards.main_menu import MAIN_MENU
from database.db import get_setting

DEFAULT_HELP = """📖 <b>راهنمای ربات SSH</b>

این ربات یک کلاینت SSH/SFTP تلگرامی است.

━━━━━━━━━━━━━━━━
🔹 <b>دستورات:</b>
/start — بازگشت به پنل اصلی
/fast_ssh — اتصال سریع (بدون ذخیره)
/my_hosts — سرورهای ذخیره شده (تا 5 تا)
/close — قطع session فعلی
/wait — بک‌گراند کردن session (15 دقیقه)

━━━━━━━━━━━━━━━━
🔹 <b>داخل ترمینال:</b>
• هر متن که بفرستی → دستور SSH
• دکمه‌ها شورتکات‌های مهم هستند
• وقتی nano/vim باز است، دکمه‌ها عوض می‌شوند

━━━━━━━━━━━━━━━━
🔹 <b>SFTP:</b>
• در اتصال سریع، SFTP را انتخاب کن
• داخل session، فایل بفرست → آپلود می‌شود (تا 20MB)

━━━━━━━━━━━━━━━━
⏰ بعد از 5 دقیقه بی‌فعالیتی، session بسته می‌شود.
🔒 رمزها با AES-256 رمزنگاری می‌شوند.
"""


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await save_user_and_track(update)
    custom = await get_setting("help_text")
    text = custom if custom else DEFAULT_HELP
    await update.message.reply_html(text, reply_markup=MAIN_MENU)
