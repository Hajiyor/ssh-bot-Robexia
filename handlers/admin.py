"""admin.py - پنل ادمین کامل و کارکردی"""

import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, ConversationHandler,
    CommandHandler, MessageHandler, CallbackQueryHandler, filters,
)

import config
from database.db import (
    get_stats, get_setting, set_setting,
    ban_user, unban_user, get_user_info,
)
from services.ssh_manager import get_manager
from services.channel_check import load_settings, save_settings, get_force_join_config
from keyboards.main_menu import MAIN_MENU, CANCEL_MENU

logger = logging.getLogger(__name__)

(AWAIT_BAN, AWAIT_UNBAN, AWAIT_CHANNEL_ID,
 AWAIT_WELCOME, AWAIT_HELP) = range(5)


def is_admin(uid: int) -> bool:
    return uid in config.ADMIN_IDS


def _get_maintenance() -> bool:
    """وضعیت maintenance را از settings.json می‌خواند (sync)"""
    from services.channel_check import load_settings
    return load_settings().get("maintenance", False)


def _set_maintenance(val: bool):
    """وضعیت maintenance را در settings.json ذخیره می‌کند (sync)"""
    cfg = load_settings()
    cfg["maintenance"] = val
    save_settings(cfg)


def _get_fj_status() -> tuple:
    cfg = get_force_join_config()
    enabled = cfg.get("enabled", False)
    channel = cfg.get("channel_username") or str(cfg.get("channel_id") or "تنظیم نشده")
    return enabled, channel


def admin_kb(maintenance: bool, fj_enabled: bool) -> InlineKeyboardMarkup:
    """کیبورد اصلی ادمین با وضعیت واقعی دکمه‌ها"""
    maint_btn = "🔴 ربات: تعمیر" if maintenance else "🟢 ربات: آنلاین"
    fj_btn = "📢 جوین: ✅ فعال" if fj_enabled else "📢 جوین: ❌ غیرفعال"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 آمار", callback_data="adm:stats"),
         InlineKeyboardButton("🔌 Session ها", callback_data="adm:sessions")],
        [InlineKeyboardButton("🚫 بن کاربر", callback_data="adm:ban"),
         InlineKeyboardButton("✅ انبن کاربر", callback_data="adm:unban")],
        [InlineKeyboardButton(fj_btn, callback_data="adm:fj_toggle"),
         InlineKeyboardButton("📢 تنظیم کانال", callback_data="adm:fj_channel")],
        [InlineKeyboardButton(maint_btn, callback_data="adm:maint_toggle")],
        [InlineKeyboardButton("✏️ متن خوش‌آمدگویی", callback_data="adm:welcome"),
         InlineKeyboardButton("📖 متن راهنما", callback_data="adm:helptext")],
    ])


async def _send_admin_panel(bot, chat_id: int, edit_msg=None):
    """ارسال یا ادیت پنل ادمین با وضعیت به‌روز"""
    maintenance = _get_maintenance()
    fj_enabled, _ = _get_fj_status()
    kb = admin_kb(maintenance, fj_enabled)
    text = "🛠 <b>پنل مدیریت</b>"
    if edit_msg:
        try:
            await edit_msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=kb)
    else:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=kb)


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    await _send_admin_panel(context.bot, update.effective_chat.id)
    return ConversationHandler.END


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔ دسترسی ندارید.", show_alert=True)
        return ConversationHandler.END

    await query.answer()
    action = query.data.split(":")[1]

    # ─── آمار ───────────────────────────────────────────────────
    if action == "stats":
        stats = await get_stats()
        mgr_stats = await get_manager().get_stats()
        maintenance = _get_maintenance()
        text = (
            "📊 <b>آمار ربات</b>\n\n"
            f"👥 کل کاربران: <b>{stats['total_users']}</b>\n"
            f"✅ کاربران فعال: <b>{stats['active_users']}</b>\n"
            f"🚫 بن‌شده: <b>{stats['banned_users']}</b>\n"
            f"📅 امروز: <b>{stats['today_users']}</b>\n\n"
            f"🖥 سرورهای ذخیره شده: <b>{stats['total_hosts']}</b>\n"
            f"🔌 کل اتصالات SSH: <b>{stats['total_ssh']}</b>\n"
            f"📅 اتصالات امروز: <b>{stats['today_ssh']}</b>\n\n"
            f"⚡ Session فعال: <b>{mgr_stats['active']}</b>\n"
            f"⏸ Session انتظار: <b>{mgr_stats['waiting']}</b>\n\n"
            f"وضعیت: {'🔴 تعمیر' if maintenance else '🟢 آنلاین'}"
        )
        maintenance = _get_maintenance()
        fj_enabled, _ = _get_fj_status()
        back_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 بازگشت", callback_data="adm:back"),
            InlineKeyboardButton("🔄 بروزرسانی", callback_data="adm:stats"),
        ]])
        try:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=back_kb)
        except Exception:
            pass
        return ConversationHandler.END

    # ─── Session ها ─────────────────────────────────────────────
    if action == "sessions":
        mgr = get_manager()
        if not mgr.sessions:
            text = "هیچ session فعالی نیست."
        else:
            lines = ["🔌 <b>Session های فعال:</b>\n"]
            for uid, s in mgr.sessions.items():
                icon = "⚡" if s.state == "active" else "⏸"
                lines.append(f"{icon} <code>{uid}</code> → {s.username}@{s.host}:{s.port}")
            text = "\n".join(lines)
        back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="adm:back")]])
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=back_kb)
        return ConversationHandler.END

    # ─── بن ─────────────────────────────────────────────────────
    if action == "ban":
        await query.edit_message_text("🚫 آیدی عددی کاربر را بفرست:", parse_mode="HTML")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="آیدی:", reply_markup=CANCEL_MENU
        )
        return AWAIT_BAN

    if action == "unban":
        await query.edit_message_text("✅ آیدی عددی کاربر را بفرست:", parse_mode="HTML")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="آیدی:", reply_markup=CANCEL_MENU
        )
        return AWAIT_UNBAN

    # ─── جوین اجباری: toggle ────────────────────────────────────
    if action == "fj_toggle":
        cfg = load_settings()
        fj = cfg.get("force_join", {})
        fj["enabled"] = not fj.get("enabled", False)
        cfg["force_join"] = fj
        save_settings(cfg)
        await _send_admin_panel(context.bot, query.message.chat_id, edit_msg=query.message)
        return ConversationHandler.END

    # ─── جوین اجباری: تنظیم کانال ──────────────────────────────
    if action == "fj_channel":
        enabled, channel = _get_fj_status()
        await query.edit_message_text(
            f"📢 <b>تنظیم جوین اجباری</b>\n\n"
            f"کانال فعلی: <code>{channel}</code>\n\n"
            f"<b>مرحله ۱:</b> لینک دعوت کانال رو بفرست\n"
            f"(مثال: <code>https://t.me/mychannel</code> یا <code>@mychannel</code>)",
            parse_mode="HTML",
        )
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="لینک کانال:", reply_markup=CANCEL_MENU,
        )
        context.user_data["fj_step"] = "link"
        return AWAIT_CHANNEL_ID

    # ─── Maintenance toggle ──────────────────────────────────────
    if action == "maint_toggle":
        current = _get_maintenance()
        _set_maintenance(not current)
        await _send_admin_panel(context.bot, query.message.chat_id, edit_msg=query.message)
        return ConversationHandler.END

    # ─── تغییر متن‌ها ────────────────────────────────────────────
    if action == "welcome":
        current = await get_setting("welcome_text") or "(پیش‌فرض)"
        await query.edit_message_text(
            f"✏️ <b>متن فعلی خوش‌آمدگویی:</b>\n\n{current[:300]}\n\n"
            "متن جدید بفرست. برای ریست: <code>reset</code>",
            parse_mode="HTML",
        )
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="متن جدید:", reply_markup=CANCEL_MENU,
        )
        return AWAIT_WELCOME

    if action == "helptext":
        current = await get_setting("help_text") or "(پیش‌فرض)"
        await query.edit_message_text(
            f"📖 <b>متن فعلی راهنما:</b>\n\n{current[:300]}\n\n"
            "متن جدید بفرست. برای ریست: <code>reset</code>",
            parse_mode="HTML",
        )
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="متن جدید:", reply_markup=CANCEL_MENU,
        )
        return AWAIT_HELP

    # ─── بازگشت ─────────────────────────────────────────────────
    if action == "back":
        await _send_admin_panel(context.bot, query.message.chat_id, edit_msg=query.message)
        return ConversationHandler.END

    return ConversationHandler.END


# ─── دریافت ورودی‌ها ─────────────────────────────────────────────

async def recv_ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    text = update.message.text.strip()
    if text == "🚫 لغو":
        await update.message.reply_text("❌ لغو شد.", reply_markup=MAIN_MENU)
        return ConversationHandler.END
    try:
        uid = int(text)
    except ValueError:
        await update.message.reply_text("❌ آیدی باید عدد باشد.")
        return AWAIT_BAN

    await ban_user(uid)
    info = await get_user_info(uid)
    name = info.get("first_name", "ناشناس") if info else "ناشناس"
    # بستن session فعال
    try:
        await get_manager().close_session(uid)
    except Exception:
        pass
    await update.message.reply_html(
        f"🚫 کاربر <b>{name}</b> (<code>{uid}</code>) بن شد.",
        reply_markup=MAIN_MENU,
    )
    return ConversationHandler.END


async def recv_unban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    text = update.message.text.strip()
    if text == "🚫 لغو":
        await update.message.reply_text("❌ لغو شد.", reply_markup=MAIN_MENU)
        return ConversationHandler.END
    try:
        uid = int(text)
    except ValueError:
        await update.message.reply_text("❌ آیدی باید عدد باشد.")
        return AWAIT_UNBAN

    await unban_user(uid)
    info = await get_user_info(uid)
    name = info.get("first_name", "ناشناس") if info else "ناشناس"
    await update.message.reply_html(
        f"✅ کاربر <b>{name}</b> (<code>{uid}</code>) انبن شد.",
        reply_markup=MAIN_MENU,
    )
    return ConversationHandler.END


async def recv_channel_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    text = update.message.text.strip()
    if text == "🚫 لغو":
        await update.message.reply_text("❌ لغو شد.", reply_markup=MAIN_MENU)
        return ConversationHandler.END

    step = context.user_data.get("fj_step", "link")

    if step == "link":
        # ذخیره لینک و درخواست ID
        context.user_data["fj_link"] = text
        context.user_data["fj_step"] = "id"
        await update.message.reply_html(
            f"✅ لینک: <code>{text}</code>\n\n"
            "<b>مرحله ۲:</b> آیدی عددی کانال رو بفرست\n"
            "(مثال: <code>-1001234567890</code>)\n\n"
            "💡 برای گرفتن ID کانال، ربات @userinfobot رو به کانال اضافه کن یا از @getmyid_bot استفاده کن.",
            reply_markup=CANCEL_MENU,
        )
        return AWAIT_CHANNEL_ID

    elif step == "id":
        link = context.user_data.pop("fj_link", "")
        context.user_data.pop("fj_step", None)

        try:
            channel_id = int(text)
        except ValueError:
            await update.message.reply_text("❌ آیدی باید عدد باشد. مثلاً: -1001234567890")
            return AWAIT_CHANNEL_ID

        cfg = load_settings()
        fj = cfg.get("force_join", {})
        fj["channel_link"] = link
        fj["channel_username"] = link if link.startswith("@") else ""
        fj["channel_id"] = channel_id
        cfg["force_join"] = fj
        save_settings(cfg)

        await update.message.reply_html(
            f"✅ جوین اجباری تنظیم شد!\n\n"
            f"📎 لینک: <code>{link}</code>\n"
            f"🆔 آیدی: <code>{channel_id}</code>\n\n"
            f"⚠️ مطمئن شو ربات ادمین کانال هست تا بتونه عضویت رو چک کنه.",
            reply_markup=MAIN_MENU,
        )
        return ConversationHandler.END


async def recv_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    text = update.message.text
    if text.strip() == "🚫 لغو":
        await update.message.reply_text("❌ لغو شد.", reply_markup=MAIN_MENU)
        return ConversationHandler.END
    if text.strip().lower() == "reset":
        await set_setting("welcome_text", "")
        await update.message.reply_html("✅ متن به پیش‌فرض برگشت.", reply_markup=MAIN_MENU)
    else:
        await set_setting("welcome_text", text)
        await update.message.reply_html("✅ متن خوش‌آمدگویی ذخیره شد.", reply_markup=MAIN_MENU)
    return ConversationHandler.END


async def recv_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    text = update.message.text
    if text.strip() == "🚫 لغو":
        await update.message.reply_text("❌ لغو شد.", reply_markup=MAIN_MENU)
        return ConversationHandler.END
    if text.strip().lower() == "reset":
        await set_setting("help_text", "")
        await update.message.reply_html("✅ متن راهنما به پیش‌فرض برگشت.", reply_markup=MAIN_MENU)
    else:
        await set_setting("help_text", text)
        await update.message.reply_html("✅ متن راهنما ذخیره شد.", reply_markup=MAIN_MENU)
    return ConversationHandler.END


def build_admin_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("admin", admin_command),
            CallbackQueryHandler(admin_callback, pattern=r"^adm:"),
        ],
        states={
            AWAIT_BAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_ban)],
            AWAIT_UNBAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_unban)],
            AWAIT_CHANNEL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_channel_id)],
            AWAIT_WELCOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_welcome)],
            AWAIT_HELP: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_help)],
        },
        fallbacks=[
            CommandHandler("admin", admin_command),
            MessageHandler(filters.Regex(r"^🚫 لغو$"), lambda u, c: ConversationHandler.END),
        ],
        name="admin_conv",
        persistent=False,
        allow_reentry=True,
    )
