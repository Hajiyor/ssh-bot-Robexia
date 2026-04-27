"""
start.py - هندلر /start

وقتی /start زده می‌شود:
1. SSH session بسته می‌شود
2. همه user_data پاک می‌شود (conversation ها ریست)
3. جوین اجباری چک می‌شود
4. پنل اصلی نمایش داده می‌شود

متن خوش‌آمدگویی از DB خوانده می‌شود (قابل تغییر توسط ادمین)
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from handlers.stats import save_user_and_track
from services.channel_check import is_user_joined, get_join_keyboard
from services.ssh_manager import get_manager
from keyboards.main_menu import MAIN_MENU
from keyboards.inline import join_channel_keyboard
from database.db import get_setting, is_banned

logger = logging.getLogger(__name__)

DEFAULT_WELCOME = (
    "👋 سلام <b>{name}</b>!\n\n"
    "به ربات SSH خوش اومدی.\n"
    "از اینجا می‌تونی از طریق تلگرام به سرورهات SSH بزنی.\n\n"
    "⚡ <b>اتصال سریع</b> — بدون ذخیره\n"
    "📋 <b>سرورهای من</b> — مدیریت سرورها (تا 5 تا)\n"
    "❓ <b>راهنما</b> — آموزش کامل"
)


async def get_welcome_text(name: str) -> str:
    """متن خوش‌آمدگویی - از DB یا پیش‌فرض"""
    custom = await get_setting("welcome_text")
    template = custom if custom else DEFAULT_WELCOME
    return template.replace("{name}", name)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """/start"""
    await save_user_and_track(update)

    user = update.effective_user
    user_id = user.id

    # چک بن
    if await is_banned(user_id):
        await update.message.reply_html("🚫 شما از ربات مسدود شده‌اید.")
        return ConversationHandler.END

    # 1. بستن SSH session فعال
    try:
        mgr = get_manager()
        if mgr.get_session(user_id):
            await mgr.close_session(user_id)
    except Exception as e:
        logger.warning(f"Error closing session on /start: {e}")

    # 2. ریست کامل user_data + خروج از SFTP mode
    from handlers.sftp import exit_sftp
    exit_sftp(context)
    context.user_data.clear()

    # 3. چک جوین اجباری
    joined = await is_user_joined(context.bot, user_id)
    if not joined:
        kb = get_join_keyboard()
        await update.message.reply_html(
            "🔔 <b>برای استفاده از ربات، ابتدا در کانال ما عضو شو.</b>\n\n"
            "بعد از عضویت، دکمه «✅ عضو شدم» را بزن.",
            reply_markup=kb,
        )
        return ConversationHandler.END

    # 4. پنل اصلی
    text = await get_welcome_text(user.first_name or "کاربر")
    await update.message.reply_html(text, reply_markup=MAIN_MENU)
    return ConversationHandler.END


async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دکمه «عضو شدم»"""
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if await is_banned(user.id):
        await query.answer("🚫 مسدود شده‌اید.", show_alert=True)
        return

    joined = await is_user_joined(context.bot, user.id)
    if not joined:
        await query.answer("❌ هنوز عضو نشدی! اول کانال رو باز کن و عضو بشو.", show_alert=True)
        return

    try:
        await query.message.delete()
    except Exception:
        pass

    text = await get_welcome_text(user.first_name or "کاربر")
    await context.bot.send_message(
        chat_id=user.id, text=text,
        parse_mode="HTML", reply_markup=MAIN_MENU,
    )
