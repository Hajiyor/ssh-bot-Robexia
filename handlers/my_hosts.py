"""
هندلر /my_hosts - مدیریت سرورهای ذخیره شده کاربر.
شامل:
- نمایش لیست
- افزودن سرور جدید (wizard چند مرحله‌ای)
- ویرایش فیلدها
- حذف با تأیید
- اتصال به سرور
"""

import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)

from handlers.stats import save_user_and_track
from database import db
from services import encryption
from services.ssh_manager import get_manager
from keyboards.main_menu import MAIN_MENU, CANCEL_MENU
from keyboards.terminal_kb import TERMINAL_NORMAL as TERMINAL_MENU
from keyboards import inline as inline_kb

logger = logging.getLogger(__name__)

# states برای افزودن/ویرایش
(ADD_NAME, ADD_HOST, ADD_PORT, ADD_USERNAME, ADD_AUTH_TYPE,
 ADD_PASSWORD, ADD_KEY, ADD_KEY_PASSPHRASE,
 EDIT_VALUE) = range(9)


# ============================================================
# نمایش لیست (/my_hosts)
# ============================================================

async def my_hosts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """نمایش لیست سرورهای کاربر"""
    await save_user_and_track(update)
    user_id = update.effective_user.id

    hosts = await db.get_user_hosts(user_id)

    if not hosts:
        await update.message.reply_html(
            "📭 <b>هنوز هیچ سروری اضافه نکردی.</b>\n\n"
            "می‌تونی تا <b>5 سرور</b> ذخیره کنی. افزودن اولین سرور:",
            reply_markup=inline_kb.empty_hosts_keyboard(),
        )
    else:
        count = len(hosts)
        await update.message.reply_html(
            f"📋 <b>سرورهای من</b> ({count}/{db.MAX_HOSTS_PER_USER})\n\n"
            "روی یک سرور کلیک کن تا جزئیاتش رو ببینی:",
            reply_markup=inline_kb.hosts_list_keyboard(hosts),
        )
    return ConversationHandler.END


async def show_host_details(query, user_id: int, host_id: int):
    """نمایش جزئیات یک سرور خاص"""
    host = await db.get_host_by_id(host_id, user_id)
    if not host:
        await query.answer("سرور یافت نشد.", show_alert=True)
        return

    auth_label = "🔑 رمز عبور" if host["auth_type"] == "password" else "🗝 کلید SSH"
    text = (
        f"🖥 <b>{host['name']}</b>\n\n"
        f"🌐 آدرس: <code>{host['host']}</code>\n"
        f"🔢 پورت: <code>{host['port']}</code>\n"
        f"👤 یوزرنیم: <code>{host['username']}</code>\n"
        f"🔐 احراز هویت: {auth_label}\n"
        f"📅 افزوده شده: <code>{host['created_at']}</code>"
    )
    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=inline_kb.host_actions_keyboard(host_id),
    )


async def hosts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """روتر اصلی همه callback های مربوط به hosts"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    await query.answer()

    if data == "host_list":
        hosts = await db.get_user_hosts(user_id)
        if not hosts:
            await query.edit_message_text(
                "📭 هیچ سروری نداری.",
                reply_markup=inline_kb.empty_hosts_keyboard(),
            )
        else:
            count = len(hosts)
            await query.edit_message_text(
                f"📋 <b>سرورهای من</b> ({count}/{db.MAX_HOSTS_PER_USER})\n\n"
                "روی یک سرور کلیک کن تا جزئیاتش رو ببینی:",
                parse_mode="HTML",
                reply_markup=inline_kb.hosts_list_keyboard(hosts),
            )
        return

    if data.startswith("host_view:"):
        host_id = int(data.split(":", 1)[1])
        await show_host_details(query, user_id, host_id)
        return

    if data.startswith("host_connect:"):
        parts = data.split(":")
        host_id = int(parts[1])
        mode = parts[2] if len(parts) > 2 else "ssh"
        await _connect_to_saved_host(update, context, host_id, mode=mode)
        return

    if data.startswith("host_delete:"):
        host_id = int(data.split(":", 1)[1])
        host = await db.get_host_by_id(host_id, user_id)
        if not host:
            await query.answer("سرور یافت نشد.", show_alert=True)
            return
        await query.edit_message_text(
            f"⚠️ آیا از حذف سرور <b>{host['name']}</b> مطمئنی؟\n\n"
            f"این عمل قابل بازگشت نیست.",
            parse_mode="HTML",
            reply_markup=inline_kb.confirm_delete_keyboard(host_id),
        )
        return

    if data.startswith("host_delete_confirm:"):
        host_id = int(data.split(":", 1)[1])
        ok = await db.delete_host(host_id, user_id)
        if ok:
            await query.answer("✅ سرور حذف شد.", show_alert=False)
            # برگشت به لیست
            hosts = await db.get_user_hosts(user_id)
            if hosts:
                count = len(hosts)
                await query.edit_message_text(
                    f"📋 <b>سرورهای من</b> ({count}/{db.MAX_HOSTS_PER_USER})",
                    parse_mode="HTML",
                    reply_markup=inline_kb.hosts_list_keyboard(hosts),
                )
            else:
                await query.edit_message_text(
                    "📭 هیچ سروری نداری.",
                    reply_markup=inline_kb.empty_hosts_keyboard(),
                )
        else:
            await query.answer("❌ خطا در حذف.", show_alert=True)
        return

    if data.startswith("host_edit:"):
        host_id = int(data.split(":", 1)[1])
        await query.edit_message_text(
            "✏️ کدوم فیلد رو می‌خوای ویرایش کنی؟",
            reply_markup=inline_kb.edit_field_keyboard(host_id),
        )
        return

    if data.startswith("edit_field:"):
        # edit_field:<host_id>:<field_name>
        parts = data.split(":")
        host_id = int(parts[1])
        field = parts[2]
        await _start_edit_field(update, context, host_id, field)
        return


async def _connect_to_saved_host(update, context, host_id: int, mode: str = "ssh"):
    """اتصال به یک سرور ذخیره شده - SSH یا SFTP"""
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = query.message.chat_id

    manager = get_manager()
    if manager.get_session(user_id):
        await query.answer("⚠️ یک session فعال داری. اول /close بزن.", show_alert=True)
        return

    host = await db.get_host_by_id(host_id, user_id)
    if not host:
        await query.answer("سرور یافت نشد.", show_alert=True)
        return

    password = None
    private_key = None
    key_passphrase = None

    if host["auth_type"] == "password" and host["password_enc"]:
        password = await encryption.decrypt(user_id, host["password_enc"])
        if password is None:
            await query.edit_message_text("❌ خطا در رمزگشایی رمز.")
            return
    elif host["auth_type"] == "key" and host["key_enc"]:
        private_key = await encryption.decrypt(user_id, host["key_enc"])
        if host["key_passphrase_enc"]:
            key_passphrase = await encryption.decrypt(user_id, host["key_passphrase_enc"])
        if private_key is None:
            await query.edit_message_text("❌ خطا در رمزگشایی کلید.")
            return

    mode_label = "📂 SFTP" if mode == "sftp" else "🖥 SSH"
    await query.edit_message_text(
        f"🔄 {mode_label} - اتصال به <b>{host['name']}</b>...",
        parse_mode="HTML",
    )

    success, msg = await manager.connect(
        user_id=user_id, chat_id=chat_id,
        host=host["host"], port=host["port"],
        username=host["username"],
        password=password, private_key=private_key, key_passphrase=key_passphrase,
    )

    if success and mode == "sftp":
        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")
        from handlers.sftp import sftp_entry
        await sftp_entry(context, user_id, chat_id)
    else:
        from keyboards.terminal_kb import TERMINAL_NORMAL
        from handlers.sftp import SSH_CONNECTED_HELP
        if success:
            full_msg = msg + "\n\n" + SSH_CONNECTED_HELP
        else:
            full_msg = msg
        await context.bot.send_message(
            chat_id=chat_id, text=full_msg, parse_mode="HTML",
            reply_markup=TERMINAL_NORMAL if success else MAIN_MENU,
        )


# ============================================================
# افزودن سرور جدید (wizard)
# ============================================================

async def add_host_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """شروع wizard افزودن از callback"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    count = await db.count_user_hosts(user_id)
    if count >= db.MAX_HOSTS_PER_USER:
        await query.edit_message_text(
            f"❌ به حداکثر تعداد سرور ({db.MAX_HOSTS_PER_USER}) رسیدی.\n"
            f"اول یکی از سرورها رو حذف کن تا بتونی اضافه کنی."
        )
        return ConversationHandler.END

    context.user_data["add_host"] = {}
    await query.edit_message_text(
        "➕ <b>افزودن سرور جدید</b>\n\n"
        "🔹 مرحله 1/5: یک <b>نام</b> برای این سرور انتخاب کن (مثل «سرور اصلی»):",
        parse_mode="HTML",
    )
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="نام سرور رو بفرست:",
        reply_markup=CANCEL_MENU,
    )
    return ADD_NAME


async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "🚫 لغو":
        return await add_cancel(update, context)
    if not text or len(text) > 50:
        await update.message.reply_text("❌ نام باید بین 1 تا 50 کاراکتر باشه.")
        return ADD_NAME

    context.user_data["add_host"]["name"] = text
    await update.message.reply_html(
        f"✅ نام: <code>{text}</code>\n\n"
        "🔹 مرحله 2/5: <b>آدرس سرور</b> رو بفرست (IP یا دامنه):",
        reply_markup=CANCEL_MENU,
    )
    return ADD_HOST


async def add_host_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "🚫 لغو":
        return await add_cancel(update, context)
    if not text or len(text) > 255:
        await update.message.reply_text("❌ آدرس نامعتبره.")
        return ADD_HOST

    context.user_data["add_host"]["host"] = text
    await update.message.reply_html(
        f"✅ آدرس: <code>{text}</code>\n\n"
        "🔹 مرحله 3/5: <b>پورت SSH</b> رو بفرست (پیش‌فرض 22 - می‌تونی <code>22</code> بفرستی):",
        reply_markup=CANCEL_MENU,
    )
    return ADD_PORT


async def add_port(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "🚫 لغو":
        return await add_cancel(update, context)

    try:
        port = int(text)
        if not (1 <= port <= 65535):
            raise ValueError()
    except ValueError:
        await update.message.reply_text("❌ پورت نامعتبر. عدد بین 1 تا 65535 بفرست.")
        return ADD_PORT

    context.user_data["add_host"]["port"] = port
    await update.message.reply_html(
        f"✅ پورت: <code>{port}</code>\n\n"
        "🔹 مرحله 4/5: <b>یوزرنیم SSH</b> رو بفرست:",
        reply_markup=CANCEL_MENU,
    )
    return ADD_USERNAME


async def add_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "🚫 لغو":
        return await add_cancel(update, context)
    if not text or len(text) > 64:
        await update.message.reply_text("❌ یوزرنیم نامعتبره.")
        return ADD_USERNAME

    context.user_data["add_host"]["username"] = text
    await update.message.reply_html(
        f"✅ یوزرنیم: <code>{text}</code>\n\n"
        "🔹 مرحله 5/5: <b>نوع احراز هویت</b> رو انتخاب کن:",
        reply_markup=inline_kb.auth_type_keyboard(),
    )
    return ADD_AUTH_TYPE


async def add_auth_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    auth_type = query.data.split(":", 1)[1]
    context.user_data["add_host"]["auth_type"] = auth_type

    if auth_type == "password":
        await query.edit_message_text("🔑 <b>رمز عبور</b> رو بفرست:", parse_mode="HTML")
        return ADD_PASSWORD
    else:
        await query.edit_message_text(
            "🗝 <b>کلید خصوصی SSH</b> (محتوای .pem یا .key) رو کامل بفرست.\n\n"
            "می‌تونی به صورت متن یا به صورت فایل بفرستی.",
            parse_mode="HTML",
        )
        return ADD_KEY


async def add_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    password = update.message.text
    if password.strip() == "🚫 لغو":
        return await add_cancel(update, context)

    # حذف پیام رمز برای امنیت
    try:
        await update.message.delete()
    except Exception:
        pass

    context.user_data["add_host"]["password"] = password
    return await _finalize_add(update, context)


async def add_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """دریافت کلید SSH به صورت متن یا فایل"""
    # دریافت از فایل
    if update.message.document:
        doc = update.message.document
        if doc.file_size > 1024 * 100:  # حداکثر 100KB برای کلید
            await update.message.reply_text("❌ فایل کلید بیش از حد بزرگه.")
            return ADD_KEY
        try:
            f = await doc.get_file()
            ba = await f.download_as_bytearray()
            key_text = bytes(ba).decode("utf-8", errors="replace")
        except Exception as e:
            await update.message.reply_text(f"❌ خطا در خواندن فایل: {e}")
            return ADD_KEY
    else:
        text = update.message.text
        if text and text.strip() == "🚫 لغو":
            return await add_cancel(update, context)
        key_text = text

    if not key_text or "BEGIN" not in key_text:
        await update.message.reply_text(
            "❌ این به نظر یک کلید خصوصی معتبر نمیاد. کلید SSH باید با '-----BEGIN' شروع بشه."
        )
        return ADD_KEY

    # تلاش برای parse کردن (برای اعتبارسنجی)
    import asyncssh
    try:
        asyncssh.import_private_key(key_text)
        context.user_data["add_host"]["private_key"] = key_text
        context.user_data["add_host"]["key_passphrase"] = None
    except asyncssh.KeyImportError as e:
        if "passphrase" in str(e).lower():
            # کلید رمزدار است
            context.user_data["add_host"]["private_key"] = key_text
            try:
                await update.message.delete()
            except Exception:
                pass
            await update.message.reply_html(
                "🔐 این کلید رمز داره. <b>passphrase</b> رو بفرست:",
                reply_markup=CANCEL_MENU,
            )
            return ADD_KEY_PASSPHRASE
        else:
            await update.message.reply_text(f"❌ کلید نامعتبره: {e}")
            return ADD_KEY

    # حذف پیام کلید برای امنیت
    try:
        await update.message.delete()
    except Exception:
        pass

    return await _finalize_add(update, context)


async def add_key_passphrase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    passphrase = update.message.text
    if passphrase.strip() == "🚫 لغو":
        return await add_cancel(update, context)

    # بررسی صحت passphrase
    import asyncssh
    try:
        asyncssh.import_private_key(
            context.user_data["add_host"]["private_key"],
            passphrase=passphrase,
        )
    except asyncssh.KeyImportError:
        await update.message.reply_text("❌ passphrase اشتباهه. دوباره بفرست یا 🚫 لغو:")
        return ADD_KEY_PASSPHRASE

    try:
        await update.message.delete()
    except Exception:
        pass

    context.user_data["add_host"]["key_passphrase"] = passphrase
    return await _finalize_add(update, context)


async def _finalize_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """ذخیره نهایی سرور در دیتابیس"""
    data = context.user_data["add_host"]
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    password_enc = None
    key_enc = None
    key_passphrase_enc = None

    if data["auth_type"] == "password":
        password_enc = await encryption.encrypt(user_id, data["password"])
    else:
        key_enc = await encryption.encrypt(user_id, data["private_key"])
        if data.get("key_passphrase"):
            key_passphrase_enc = await encryption.encrypt(user_id, data["key_passphrase"])

    host_id = await db.add_host(
        user_id=user_id,
        name=data["name"],
        host=data["host"],
        port=data["port"],
        username=data["username"],
        auth_type=data["auth_type"],
        password_enc=password_enc,
        key_enc=key_enc,
        key_passphrase_enc=key_passphrase_enc,
    )

    context.user_data.pop("add_host", None)

    if host_id is None:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ نتونستم ذخیره کنم. احتمالاً به سقف {db.MAX_HOSTS_PER_USER} سرور رسیدی.",
            reply_markup=MAIN_MENU,
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"✅ سرور <b>{data['name']}</b> با موفقیت ذخیره شد!\n\n"
                f"از منو <code>📋 سرورهای من</code> می‌تونی بهش وصل بشی."
            ),
            parse_mode="HTML",
            reply_markup=MAIN_MENU,
        )
    return ConversationHandler.END


async def add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("add_host", None)
    msg = "❌ افزودن سرور لغو شد."
    if update.message:
        await update.message.reply_text(msg, reply_markup=MAIN_MENU)
    elif update.callback_query:
        await update.callback_query.edit_message_text(msg)
    return ConversationHandler.END


# ============================================================
# ویرایش فیلد یک سرور
# ============================================================

async def _start_edit_field(update, context, host_id: int, field: str):
    """شروع ویرایش یک فیلد"""
    query = update.callback_query
    user_id = query.from_user.id

    host = await db.get_host_by_id(host_id, user_id)
    if not host:
        await query.answer("سرور یافت نشد.", show_alert=True)
        return ConversationHandler.END

    context.user_data["edit"] = {"host_id": host_id, "field": field}

    prompts = {
        "name": "📛 نام جدید رو بفرست:",
        "host": "🌐 آدرس جدید رو بفرست:",
        "port": "🔢 پورت جدید رو بفرست (عدد بین 1-65535):",
        "username": "👤 یوزرنیم جدید رو بفرست:",
        "auth": "🔐 روش جدید احراز هویت رو انتخاب کن:",
    }

    if field == "auth":
        await query.edit_message_text(
            prompts[field],
            reply_markup=inline_kb.auth_type_keyboard(),
        )
        # reuse add flow from ADD_AUTH_TYPE
        context.user_data["edit_mode"] = True
        return ConversationHandler.END

    await query.edit_message_text(prompts[field])
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="مقدار جدید رو بفرست (یا 🚫 لغو):",
        reply_markup=CANCEL_MENU,
    )
    return EDIT_VALUE


async def edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """دریافت مقدار جدید و ذخیره"""
    text = update.message.text.strip()
    if text == "🚫 لغو":
        context.user_data.pop("edit", None)
        await update.message.reply_text("❌ ویرایش لغو شد.", reply_markup=MAIN_MENU)
        return ConversationHandler.END

    edit_info = context.user_data.get("edit")
    if not edit_info:
        return ConversationHandler.END

    field = edit_info["field"]
    host_id = edit_info["host_id"]
    user_id = update.effective_user.id

    # اعتبارسنجی
    if field == "port":
        try:
            value = int(text)
            if not (1 <= value <= 65535):
                raise ValueError()
        except ValueError:
            await update.message.reply_text("❌ پورت نامعتبر.")
            return EDIT_VALUE
    elif field in ("name", "host", "username"):
        if not text or len(text) > 255:
            await update.message.reply_text("❌ مقدار نامعتبر.")
            return EDIT_VALUE
        value = text
    else:
        await update.message.reply_text("❌ فیلد نامعتبر.")
        context.user_data.pop("edit", None)
        return ConversationHandler.END

    ok = await db.update_host(host_id, user_id, **{field: value})
    context.user_data.pop("edit", None)

    if ok:
        await update.message.reply_html(
            f"✅ فیلد <b>{field}</b> به‌روز شد.",
            reply_markup=MAIN_MENU,
        )
    else:
        await update.message.reply_text("❌ خطا در ذخیره.", reply_markup=MAIN_MENU)

    return ConversationHandler.END


# ============================================================
# ساخت ConversationHandler ها
# ============================================================

def build_my_hosts_command_handler():
    """هندلر ساده برای /my_hosts و دکمه منو"""
    return [
        CommandHandler("my_hosts", my_hosts_command),
        MessageHandler(filters.Regex(r"^📋 سرورهای من$"), my_hosts_command),
    ]


def build_add_host_handler() -> ConversationHandler:
    """ConversationHandler برای افزودن سرور (ورود از callback host_add)"""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(add_host_start_callback, pattern=r"^host_add$"),
        ],
        states={
            ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            ADD_HOST: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_host_field)],
            ADD_PORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_port)],
            ADD_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_username)],
            ADD_AUTH_TYPE: [
                CallbackQueryHandler(add_auth_type_callback, pattern=r"^auth_type:"),
            ],
            ADD_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_password)],
            ADD_KEY: [
                MessageHandler(filters.Document.ALL | (filters.TEXT & ~filters.COMMAND), add_key),
            ],
            ADD_KEY_PASSPHRASE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_key_passphrase),
            ],
        },
        fallbacks=[
            CommandHandler("start", add_cancel),
            CommandHandler("cancel", add_cancel),
            MessageHandler(filters.Regex(r"^🚫 لغو$"), add_cancel),
        ],
        name="add_host_conv",
        persistent=False,
        allow_reentry=True,
        per_message=False,
    )


def build_edit_host_handler() -> ConversationHandler:
    """ConversationHandler برای ویرایش فیلد"""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(hosts_callback, pattern=r"^edit_field:"),
        ],
        states={
            EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_value)],
        },
        fallbacks=[
            CommandHandler("start", add_cancel),
            MessageHandler(filters.Regex(r"^🚫 لغو$"), add_cancel),
        ],
        name="edit_host_conv",
        persistent=False,
        allow_reentry=True,
        per_message=False,
    )
