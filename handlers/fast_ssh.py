"""
fast_ssh.py - اتصال سریع SSH/SFTP با SFTP browser کامل

SFTP browser:
- نمایش فایل‌ها و پوشه‌ها (با نام قابل کپی <code>)
- ناوبری (cd به جلو، برگشت به عقب)
- ساخت پوشه در مسیر فعلی
- ساخت فایل خالی در مسیر فعلی
- حذف فایل/پوشه
- انتقال فایل/پوشه
- آپلود فایل (تا 20MB)
"""

import logging
import posixpath
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton,
)
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)

from handlers.stats import save_user_and_track
from services.ssh_manager import get_manager
from keyboards.main_menu import MAIN_MENU, CANCEL_MENU
from keyboards.terminal_kb import TERMINAL_NORMAL

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 20 * 1024 * 1024

# States
(
    CHOOSE_MODE, ASK_HOST, ASK_USERNAME, ASK_PASSWORD, ASK_PORT,
    SFTP_BROWSING, SFTP_AWAIT_FILE, SFTP_AWAIT_PATH,
    SFTP_CONFIRM_MKDIR, SFTP_AWAIT_MKDIR_NAME, SFTP_AWAIT_MKFILE_NAME,
    SFTP_AWAIT_DELETE_NAME, SFTP_AWAIT_MOVE_NAME, SFTP_AWAIT_MOVE_DEST,
) = range(14)

MODE_KB = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("🖥 SSH", callback_data="fast_mode:ssh"),
        InlineKeyboardButton("📂 SFTP", callback_data="fast_mode:sftp"),
    ],
])

USERNAME_KB = ReplyKeyboardMarkup(
    [[KeyboardButton("root")], [KeyboardButton("🚫 لغو")]],
    resize_keyboard=True, one_time_keyboard=True,
)

SFTP_MENU = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📁 ساخت پوشه"), KeyboardButton("📄 ساخت فایل")],
        [KeyboardButton("🗑 حذف"), KeyboardButton("✂️ انتقال")],
        [KeyboardButton("📤 آپلود فایل"), KeyboardButton("⬆️ پوشه قبلی")],
        [KeyboardButton("🏠 Home"), KeyboardButton("🔄 رفرش")],
        [KeyboardButton("❌ بستن SFTP")],
    ],
    resize_keyboard=True, is_persistent=True,
)


def _fmt_size(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size//1024}KB"
    else:
        return f"{size//(1024*1024)}MB"


def _build_dir_text(path: str, items: list) -> str:
    """نمایش محتوای مسیر با نام‌های قابل کپی"""
    lines = [f"📂 <code>{path}</code>\n"]
    dirs = [i for i in items if i['is_dir']]
    files = [i for i in items if not i['is_dir']]
    for d in dirs[:30]:
        lines.append(f"📁 <code>{d['name']}/</code>")
    for f in files[:30]:
        lines.append(f"📄 <code>{f['name']}</code> <i>({_fmt_size(f['size'])})</i>")
    if not items:
        lines.append("<i>(پوشه خالی)</i>")
    if len(items) > 60:
        lines.append(f"\n<i>... و {len(items)-60} مورد دیگر</i>")
    return "\n".join(lines)


# ─── Entry ────────────────────────────────────────────────────────

async def fast_ssh_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await save_user_and_track(update)
    manager = get_manager()
    if manager.get_session(update.effective_user.id):
        await update.message.reply_html(
            "⚠️ یک session فعال داری. اول /close بزن."
        )
        return ConversationHandler.END

    context.user_data["fast"] = {}
    await update.message.reply_html("⚡ <b>اتصال سریع</b>\n\nنوع اتصال:", reply_markup=MODE_KB)
    return CHOOSE_MODE


async def choose_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    mode = query.data.split(":")[1]
    context.user_data["fast"]["mode"] = mode
    await query.edit_message_text(
        f"{'🖥 SSH' if mode == 'ssh' else '📂 SFTP'} انتخاب شد.\n\n"
        "آدرس سرور:\n<code>user@host</code> یا <code>user@host:port</code>",
        parse_mode="HTML",
    )
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="🌐 آدرس سرور:",
        reply_markup=CANCEL_MENU,
    )
    return ASK_HOST


async def ask_host(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "🚫 لغو":
        return await cancel(update, context)

    data = context.user_data.setdefault("fast", {})
    port = 22
    username = None
    host = text

    if "@" in text:
        username, host = text.rsplit("@", 1)
    if ":" in host:
        try:
            host, p = host.split(":", 1)
            port = int(p)
            if not (1 <= port <= 65535):
                raise ValueError()
        except ValueError:
            await update.message.reply_text("❌ پورت نامعتبر.")
            return ASK_HOST

    if not host:
        await update.message.reply_text("❌ آدرس خالی.")
        return ASK_HOST

    data["host"] = host
    data["port"] = port

    if username:
        data["username"] = username
        await update.message.reply_html(
            f"✅ <code>{username}@{host}:{port}</code>\n\n🔐 رمز عبور:",
            reply_markup=CANCEL_MENU,
        )
        return ASK_PASSWORD
    else:
        await update.message.reply_html(
            f"✅ آدرس: <code>{host}:{port}</code>\n\n👤 یوزرنیم:",
            reply_markup=USERNAME_KB,
        )
        return ASK_USERNAME


async def ask_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "🚫 لغو":
        return await cancel(update, context)
    if not text:
        await update.message.reply_text("❌ خالی.", reply_markup=USERNAME_KB)
        return ASK_USERNAME
    context.user_data["fast"]["username"] = text
    await update.message.reply_html(f"✅ <code>{text}</code>\n\n🔐 رمز عبور:", reply_markup=CANCEL_MENU)
    return ASK_PASSWORD


async def ask_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    pw = update.message.text
    if pw.strip() == "🚫 لغو":
        return await cancel(update, context)
    try:
        await update.message.delete()
    except Exception:
        pass
    context.user_data["fast"]["password"] = pw
    return await _do_connect(update, context)


async def _do_connect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = context.user_data["fast"]
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    status = await context.bot.send_message(
        chat_id=chat_id,
        text=f"🔄 اتصال به <code>{data['username']}@{data['host']}:{data['port']}</code>...",
        parse_mode="HTML",
    )

    manager = get_manager()
    ok, msg = await manager.connect(
        user_id=user_id, chat_id=chat_id,
        host=data["host"], port=data["port"],
        username=data["username"], password=data["password"],
    )
    try:
        await status.delete()
    except Exception:
        pass

    if ok:
        mode = data.get("mode", "ssh")
        context.user_data.pop("fast", None)
        if mode == "sftp":
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")
            from handlers.sftp import sftp_entry
            await sftp_entry(context, user_id, chat_id)
            return ConversationHandler.END
        else:
            from handlers.sftp import SSH_CONNECTED_HELP
            await context.bot.send_message(
                chat_id=chat_id,
                text=msg + "\n\n" + SSH_CONNECTED_HELP,
                parse_mode="HTML", reply_markup=TERMINAL_NORMAL,
            )
            return ConversationHandler.END
    else:
        if data["port"] == 22 and any(k in msg for k in ("timeout", "Timeout", "اتصال")):
            await context.bot.send_message(
                chat_id=chat_id,
                text=msg + "\n\n🔢 پورت SSH را بفرست (یا 🚫 لغو):",
                parse_mode="HTML", reply_markup=CANCEL_MENU,
            )
            return ASK_PORT
        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML", reply_markup=MAIN_MENU)
        context.user_data.pop("fast", None)
        return ConversationHandler.END


async def ask_port(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "🚫 لغو":
        return await cancel(update, context)
    try:
        port = int(text)
        if not (1 <= port <= 65535):
            raise ValueError()
    except ValueError:
        await update.message.reply_text("❌ پورت نامعتبر.")
        return ASK_PORT
    context.user_data["fast"]["port"] = port
    return await _do_connect(update, context)


# ─── SFTP Browser ─────────────────────────────────────────────────

async def _sftp_show(update: Update, context: ContextTypes.DEFAULT_TYPE, path: str) -> int:
    """نمایش محتوای مسیر SFTP"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id if update.effective_chat else update.message.chat_id

    manager = get_manager()
    ok, items, real_path = await manager.sftp_list(user_id, path)

    sftp_data = context.user_data.setdefault("sftp", {})
    if ok:
        sftp_data["current_path"] = real_path
        # نگه داشتن تاریخچه مسیر برای برگشت به عقب
        history = sftp_data.setdefault("history", [])
        if not history or history[-1] != real_path:
            history.append(real_path)
            if len(history) > 20:
                history.pop(0)

    text = _build_dir_text(real_path if ok else path, items if ok else [])
    if not ok:
        text = f"❌ خطا: {real_path}"

    await context.bot.send_message(
        chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=SFTP_MENU
    )
    return SFTP_BROWSING


async def sftp_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """روتر دکمه‌های SFTP"""
    text = update.message.text
    user_id = update.effective_user.id
    sftp_data = context.user_data.get("sftp", {})
    current = sftp_data.get("current_path", ".")

    if text == "🔄 رفرش":
        return await _sftp_show(update, context, current)

    if text == "⬆️ پوشه قبلی":
        history = sftp_data.get("history", [])
        if len(history) > 1:
            history.pop()  # حذف current
            prev = history[-1]
            sftp_data["current_path"] = prev
        else:
            prev = posixpath.dirname(current) or "/"
        return await _sftp_show(update, context, prev)

    if text == "🏠 Home":
        return await _sftp_show(update, context, "~")

    if text == "📁 ساخت پوشه":
        await update.message.reply_html(
            f"📁 نام پوشه جدید را در <code>{current}</code> بفرست:",
            reply_markup=CANCEL_MENU,
        )
        return SFTP_AWAIT_MKDIR_NAME

    if text == "📄 ساخت فایل":
        await update.message.reply_html(
            f"📄 نام فایل جدید را در <code>{current}</code> بفرست:",
            reply_markup=CANCEL_MENU,
        )
        return SFTP_AWAIT_MKFILE_NAME

    if text == "🗑 حذف":
        await update.message.reply_html(
            f"🗑 نام فایل یا پوشه‌ای که می‌خوای حذف کنی را از <code>{current}</code> بفرست:",
            reply_markup=CANCEL_MENU,
        )
        return SFTP_AWAIT_DELETE_NAME

    if text == "✂️ انتقال":
        await update.message.reply_html(
            f"✂️ نام فایل یا پوشه‌ای که می‌خوای انتقال بدی را از <code>{current}</code> بفرست:",
            reply_markup=CANCEL_MENU,
        )
        return SFTP_AWAIT_MOVE_NAME

    if text == "📤 آپلود فایل":
        await update.message.reply_html(
            f"📤 فایل رو بفرست (حداکثر 20MB).\n"
            f"در مسیر <code>{current}</code> آپلود می‌شه.",
            reply_markup=CANCEL_MENU,
        )
        return SFTP_AWAIT_FILE

    if text == "❌ بستن SFTP":
        manager = get_manager()
        await manager.close_session(user_id)
        context.user_data.pop("sftp", None)
        await update.message.reply_html("🔌 <b>SFTP بسته شد.</b>", reply_markup=MAIN_MENU)
        return ConversationHandler.END

    if text == "🚫 لغو":
        return await _sftp_show(update, context, current)

    # اگر کاربر اسم پوشه‌ای نوشت → cd
    sftp_data["pending_cd"] = text
    new_path = posixpath.join(current, text)
    return await _sftp_cd(update, context, new_path)


async def _sftp_cd(update, context, path: str) -> int:
    """تلاش برای cd به مسیر - اگر نبود پیشنهاد mkdir"""
    user_id = update.effective_user.id
    manager = get_manager()
    ok, items, real_path = await manager.sftp_list(user_id, path)
    if ok:
        sftp_data = context.user_data.setdefault("sftp", {})
        sftp_data["current_path"] = real_path
        history = sftp_data.setdefault("history", [])
        history.append(real_path)
        text = _build_dir_text(real_path, items)
        await update.message.reply_html(text, reply_markup=SFTP_MENU)
        return SFTP_BROWSING
    else:
        context.user_data["sftp"]["pending_mkdir"] = path
        await update.message.reply_html(
            f"❌ مسیر <code>{path}</code> وجود ندارد.\n\nمی‌خوای ساخته بشه؟",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ بله", callback_data="sftp_mkdir:yes"),
                    InlineKeyboardButton("❌ خیر", callback_data="sftp_mkdir:no"),
                ],
            ]),
        )
        return SFTP_CONFIRM_MKDIR


async def sftp_await_mkdir_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "🚫 لغو":
        return await _sftp_show(update, context, context.user_data.get("sftp", {}).get("current_path", "."))
    current = context.user_data.get("sftp", {}).get("current_path", ".")
    new_path = posixpath.join(current, text)
    ok, msg = await get_manager().sftp_mkdir(update.effective_user.id, new_path)
    await update.message.reply_html(msg)
    return await _sftp_show(update, context, current)


async def sftp_await_mkfile_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "🚫 لغو":
        return await _sftp_show(update, context, context.user_data.get("sftp", {}).get("current_path", "."))
    current = context.user_data.get("sftp", {}).get("current_path", ".")
    new_path = posixpath.join(current, text)
    ok, msg = await get_manager().sftp_mkfile(update.effective_user.id, new_path)
    await update.message.reply_html(msg)
    return await _sftp_show(update, context, current)


async def sftp_await_delete_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    current = context.user_data.get("sftp", {}).get("current_path", ".")
    if text == "🚫 لغو":
        return await _sftp_show(update, context, current)
    target = posixpath.join(current, text)
    ok, msg = await get_manager().sftp_delete(update.effective_user.id, target)
    await update.message.reply_html(msg)
    return await _sftp_show(update, context, current)


async def sftp_await_move_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    current = context.user_data.get("sftp", {}).get("current_path", ".")
    if text == "🚫 لغو":
        return await _sftp_show(update, context, current)
    context.user_data["sftp"]["move_src"] = posixpath.join(current, text)
    await update.message.reply_html(
        f"✂️ مسیر مقصد برای انتقال <code>{text}</code> را بفرست:\n"
        f"(مثلاً <code>/tmp/</code> یا <code>../backup/</code>)",
        reply_markup=CANCEL_MENU,
    )
    return SFTP_AWAIT_MOVE_DEST


async def sftp_await_move_dest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    current = context.user_data.get("sftp", {}).get("current_path", ".")
    if text == "🚫 لغو":
        return await _sftp_show(update, context, current)
    src = context.user_data.get("sftp", {}).get("move_src", "")
    if not src:
        return await _sftp_show(update, context, current)
    # اگر مسیر نسبی بود، نسبت به current
    if not text.startswith("/"):
        dst = posixpath.join(current, text)
    else:
        dst = text
    # اگر مقصد پوشه است، نام فایل رو اضافه کن
    dst_full = posixpath.join(dst, posixpath.basename(src)) if not dst.endswith(posixpath.basename(src)) else dst
    ok, msg = await get_manager().sftp_move(update.effective_user.id, src, dst_full)
    await update.message.reply_html(msg)
    return await _sftp_show(update, context, current)


async def sftp_await_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """دریافت فایل برای آپلود"""
    if update.message.text and update.message.text.strip() == "🚫 لغو":
        current = context.user_data.get("sftp", {}).get("current_path", ".")
        return await _sftp_show(update, context, current)

    doc = update.message.document
    if not doc:
        await update.message.reply_html("❌ فایل بفرست.", reply_markup=CANCEL_MENU)
        return SFTP_AWAIT_FILE

    if doc.file_size and doc.file_size > MAX_FILE_SIZE:
        await update.message.reply_html(f"❌ فایل بیش از 20MB است.")
        return SFTP_AWAIT_FILE

    user_id = update.effective_user.id
    current = context.user_data.get("sftp", {}).get("current_path", ".")

    status = await update.message.reply_html("⏳ دانلود از تلگرام...")
    try:
        f = await doc.get_file()
        ba = await f.download_as_bytearray()
    except Exception as e:
        await status.edit_text(f"❌ خطا: {e}")
        return SFTP_AWAIT_FILE

    await status.edit_text("⏳ آپلود به سرور...")
    ok, msg = await get_manager().sftp_upload_to_path(
        user_id=user_id, file_bytes=bytes(ba),
        filename=doc.file_name or "file", remote_dir=current,
    )
    await status.edit_text(msg, parse_mode="HTML")
    return await _sftp_show(update, context, current)


async def sftp_mkdir_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تأیید ساخت پوشه"""
    query = update.callback_query
    await query.answer()
    choice = query.data.split(":")[1]
    sftp_data = context.user_data.get("sftp", {})
    pending = sftp_data.get("pending_mkdir", "")
    current = sftp_data.get("current_path", ".")

    if choice == "yes" and pending:
        ok, msg = await get_manager().sftp_mkdir(query.from_user.id, pending)
        await query.edit_message_text(msg, parse_mode="HTML")
        if ok:
            sftp_data["current_path"] = pending
            return await _sftp_show(update, context, pending)
    else:
        await query.edit_message_text("❌ لغو شد.")

    return await _sftp_show(update, context, current)


# ─── Cancel ────────────────────────────────────────────────────────

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("fast", None)
    context.user_data.pop("sftp", None)
    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id:
        await context.bot.send_message(chat_id=chat_id, text="❌ لغو شد.", reply_markup=MAIN_MENU)
    return ConversationHandler.END


# ─── ConversationHandler ──────────────────────────────────────────

def build_fast_ssh_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("fast_ssh", fast_ssh_start),
            MessageHandler(filters.Regex(r"^⚡ اتصال سریع$"), fast_ssh_start),
        ],
        states={
            CHOOSE_MODE: [CallbackQueryHandler(choose_mode, pattern=r"^fast_mode:")],
            ASK_HOST: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_host)],
            ASK_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_username)],
            ASK_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_password)],
            ASK_PORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_port)],
            SFTP_BROWSING: [MessageHandler(filters.TEXT & ~filters.COMMAND, sftp_menu_handler)],
            SFTP_AWAIT_FILE: [
                MessageHandler(filters.Document.ALL, sftp_await_file),
                MessageHandler(filters.TEXT & ~filters.COMMAND, sftp_await_file),
            ],
            SFTP_AWAIT_PATH: [MessageHandler(filters.TEXT & ~filters.COMMAND, sftp_menu_handler)],
            SFTP_CONFIRM_MKDIR: [CallbackQueryHandler(sftp_mkdir_callback, pattern=r"^sftp_mkdir:")],
            SFTP_AWAIT_MKDIR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, sftp_await_mkdir_name)],
            SFTP_AWAIT_MKFILE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, sftp_await_mkfile_name)],
            SFTP_AWAIT_DELETE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, sftp_await_delete_name)],
            SFTP_AWAIT_MOVE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, sftp_await_move_name)],
            SFTP_AWAIT_MOVE_DEST: [MessageHandler(filters.TEXT & ~filters.COMMAND, sftp_await_move_dest)],
        },
        fallbacks=[
            CommandHandler("start", cancel),
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Regex(r"^🚫 لغو$"), cancel),
        ],
        name="fast_ssh_conv",
        persistent=False,
        allow_reentry=True,
    )

# alias برای استفاده از my_hosts
_sftp_show_dir = _sftp_show
