"""terminal.py - هندلر پیام‌های ترمینال SSH"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from handlers.stats import save_user_and_track
from services.ssh_manager import get_manager
from keyboards.main_menu import MAIN_MENU, is_main_menu_button
from keyboards.terminal_kb import (
    get_keyboard_for_mode, is_shortcut, get_shortcut_data,
)

logger = logging.getLogger(__name__)
MAX_FILE_SIZE = 20 * 1024 * 1024


async def terminal_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await save_user_and_track(update)
    user_id = update.effective_user.id
    text = update.message.text if update.message else None
    if not text:
        return

    # ─── اگر کاربر در SFTP mode است ─────────────────────────────
    from handlers.sftp import is_sftp_mode, handle_sftp_message
    if is_sftp_mode(context):
        await handle_sftp_message(update, context)
        return

    manager = get_manager()
    session = manager.get_session(user_id)

    if not session:
        if is_main_menu_button(text):
            return
        await update.message.reply_html(
            "❓ دستور نامعتبر.\n\n/start برای شروع یا /help برای راهنما.",
            reply_markup=MAIN_MENU,
        )
        return

    if session.state == "waiting":
        await manager.resume(user_id)
        kb = get_keyboard_for_mode(session.terminal_mode)
        await update.message.reply_html("▶️ <b>به session برگشتی.</b>", reply_markup=kb)

    if text == "❌ /close":
        return await close_command(update, context)
    if text == "⏸ /wait":
        return await wait_command(update, context)
    if text == "🔙 /back":
        from handlers.back import back_command
        return await back_command(update, context)

    if is_shortcut(text):
        data, needs_buffer = get_shortcut_data(text)
        if data:
            if needs_buffer and text in ("⛔ Ctrl+C", "⏸ Ctrl+Z", "🚪 Ctrl+D"):
                # raw byte + buffer جدید
                ok = await manager.send_raw_with_new_buffer(user_id, data)
            elif needs_buffer:
                # دستور کامل + buffer جدید (ls, pwd, ...)
                ok = await manager.send_command_with_new_buffer(user_id, data)
            else:
                ok = await manager.send_raw(user_id, data)
            if not ok:
                await update.message.reply_html("❌ Session قطع شده.", reply_markup=MAIN_MENU)
        return

    ok = await manager.send_command(user_id, text)
    if not ok:
        await update.message.reply_html("❌ Session قطع شده. /start بزن.", reply_markup=MAIN_MENU)


async def close_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await save_user_and_track(update)
    user_id = update.effective_user.id
    manager = get_manager()

    # اگر در SFTP mode بود
    from handlers.sftp import is_sftp_mode, exit_sftp
    if is_sftp_mode(context):
        exit_sftp(context)

    if not manager.get_session(user_id):
        await update.message.reply_html("ℹ️ هیچ session فعالی نداری.", reply_markup=MAIN_MENU)
        return
    await manager.close_session(user_id)
    await update.message.reply_html("🔌 <b>Session بسته شد.</b>", reply_markup=MAIN_MENU)


async def wait_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await save_user_and_track(update)
    user_id = update.effective_user.id
    manager = get_manager()
    session = manager.get_session(user_id)
    if not session:
        await update.message.reply_html("ℹ️ هیچ session فعالی نداری.", reply_markup=MAIN_MENU)
        return
    if session.state == "waiting":
        await update.message.reply_html("ℹ️ Session قبلاً در حالت انتظار است.")
        return
    await manager.put_on_wait(user_id)
    await update.message.reply_html(
        "⏸ <b>Session در حالت انتظار.</b>\n\nتا 15 دقیقه زنده می‌مونه.",
        reply_markup=MAIN_MENU,
    )


async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فایل دریافتی - در SFTP mode آپلود می‌کند"""
    await save_user_and_track(update)
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    doc = update.message.document

    from handlers.sftp import is_sftp_mode, handle_sftp_message
    if is_sftp_mode(context) and doc:
        await handle_sftp_message(update, context)
        return

    manager = get_manager()
    session = manager.get_session(user_id)
    if not session:
        await update.message.reply_html("❌ برای آپلود، ابتدا به سروری متصل شو.", reply_markup=MAIN_MENU)
        return
    if session.state == "waiting":
        await manager.resume(user_id)
    if not doc:
        return
    if doc.file_size and doc.file_size > MAX_FILE_SIZE:
        await update.message.reply_html("❌ فایل بیش از 20MB است.")
        return
    cur_path = context.user_data.get("sftp_path", ".")
    status = await update.message.reply_html(f"⏳ دانلود <code>{doc.file_name}</code>...")
    try:
        f = await doc.get_file()
        ba = await f.download_as_bytearray()
    except Exception as e:
        await status.edit_text(f"❌ {e}")
        return
    await status.edit_text("⏳ آپلود به سرور...")
    ok, msg = await manager.sftp_upload_to_path(user_id, bytes(ba), doc.file_name or "file", ".")
    try:
        await status.edit_text(msg, parse_mode="HTML")
    except Exception:
        await update.message.reply_html(msg)
