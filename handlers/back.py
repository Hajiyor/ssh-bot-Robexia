"""
back.py - دستور /back

عملکرد:
1. اگر session هایی در حالت wait هستند:
   - یک session → مستقیم resume
   - چند session → لیست نمایش داده می‌شود
2. اگر هیچ session فعالی نیست:
   - آخرین سرور از my_hosts (که با SSH وصل شده) را SSH می‌زند
   - فقط سرورهای داخل my_hosts (نه fast_ssh)
"""

import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CallbackQueryHandler

from handlers.stats import save_user_and_track
from services.ssh_manager import get_manager
from keyboards.main_menu import MAIN_MENU
from keyboards.terminal_kb import get_keyboard_for_mode

logger = logging.getLogger(__name__)


async def back_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/back"""
    await save_user_and_track(update)
    user_id = update.effective_user.id
    manager = get_manager()

    # ─── چک session های waiting ──────────────────────────────────
    waiting = [
        s for s in manager.sessions.values()
        if s.user_id == user_id and s.state == "waiting"
    ]

    if len(waiting) == 1:
        # یک session → مستقیم resume
        s = waiting[0]
        await manager.resume(user_id)
        kb = get_keyboard_for_mode(s.terminal_mode)
        await update.message.reply_html(
            f"▶️ <b>به session برگشتی.</b>\n"
            f"🖥 <code>{s.username}@{s.host}:{s.port}</code>",
            reply_markup=kb,
        )
        return

    if len(waiting) > 1:
        # چند session → لیست
        buttons = []
        for s in waiting:
            label = f"🖥 {s.username}@{s.host}:{s.port}"
            buttons.append([InlineKeyboardButton(label, callback_data=f"back_resume:{s.user_id}:{s.host}:{s.port}")])
        await update.message.reply_html(
            "⏸ <b>چند session در حالت انتظار داری. کدام را می‌خواهی ادامه بدی؟</b>",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    # ─── هیچ session waiting ای نیست → آخرین سرور my_hosts ──────
    try:
        from database.db import get_last_host_id, get_host_by_id
        from services import encryption

        host_id = await get_last_host_id(user_id)
        if not host_id:
            await update.message.reply_html(
                "ℹ️ هیچ session فعالی نداری و سابقه‌ای از اتصال قبلی هم وجود ندارد.\n\n"
                "از /fast_ssh یا /my_hosts استفاده کن.",
                reply_markup=MAIN_MENU,
            )
            return

        host = await get_host_by_id(host_id, user_id)
        if not host:
            await update.message.reply_html(
                "ℹ️ سرور آخر از لیست سرورهات حذف شده.\n\n"
                "از /my_hosts یک سرور انتخاب کن.",
                reply_markup=MAIN_MENU,
            )
            return

        # رمزگشایی
        password = None
        private_key = None
        key_passphrase = None

        if host["auth_type"] == "password" and host["password_enc"]:
            password = await encryption.decrypt(user_id, host["password_enc"])
        elif host["auth_type"] == "key" and host["key_enc"]:
            private_key = await encryption.decrypt(user_id, host["key_enc"])
            if host.get("key_passphrase_enc"):
                key_passphrase = await encryption.decrypt(user_id, host["key_passphrase_enc"])

        status_msg = await update.message.reply_html(
            f"🔄 اتصال مجدد به <b>{host['name']}</b> "
            f"(<code>{host['username']}@{host['host']}:{host['port']}</code>)..."
        )

        chat_id = update.effective_chat.id
        ok, msg = await manager.connect(
            user_id=user_id, chat_id=chat_id,
            host=host["host"], port=host["port"],
            username=host["username"],
            password=password, private_key=private_key, key_passphrase=key_passphrase,
        )

        try:
            await status_msg.delete()
        except Exception:
            pass

        from keyboards.terminal_kb import TERMINAL_NORMAL
        from handlers.sftp import SSH_CONNECTED_HELP

        await update.message.reply_html(
            msg + ("\n\n" + SSH_CONNECTED_HELP if ok else ""),
            reply_markup=TERMINAL_NORMAL if ok else MAIN_MENU,
        )

    except Exception as e:
        logger.exception(f"Back command error: {e}")
        await update.message.reply_html(
            "❌ خطایی رخ داد.", reply_markup=MAIN_MENU
        )


async def back_resume_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """callback برای انتخاب session از لیست"""
    query = update.callback_query
    await query.answer()

    # callback_data: back_resume:user_id:host:port
    parts = query.data.split(":")
    if len(parts) < 4:
        await query.edit_message_text("❌ خطا.")
        return

    user_id = query.from_user.id
    target_host = parts[2]
    target_port = parts[3]

    manager = get_manager()

    # پیدا کردن session مناسب
    target_session = None
    for s in manager.sessions.values():
        if (s.user_id == user_id and
                s.host == target_host and
                str(s.port) == target_port and
                s.state == "waiting"):
            target_session = s
            break

    if not target_session:
        await query.edit_message_text("❌ Session یافت نشد یا منقضی شده.")
        return

    await manager.resume(user_id)
    kb = get_keyboard_for_mode(target_session.terminal_mode)

    await query.edit_message_text(
        f"▶️ <b>به session برگشتی.</b>\n"
        f"🖥 <code>{target_session.username}@{target_session.host}:{target_session.port}</code>",
        parse_mode="HTML",
    )
    # ارسال keyboard
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="⌨️",
        reply_markup=kb,
    )


def build_back_callback() -> CallbackQueryHandler:
    return CallbackQueryHandler(back_resume_callback, pattern=r"^back_resume:")
