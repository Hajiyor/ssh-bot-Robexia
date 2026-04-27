"""
bot.py - ssh-bot-Robexia v1.0
https://github.com/Hajiyor/ssh-bot-Robexia

A Telegram SSH/SFTP client bot - Run SSH sessions directly from Telegram.
"""

import asyncio
import logging
import os
import sys
import json
import time
from logging.handlers import RotatingFileHandler

from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler,
    MessageHandler, CallbackQueryHandler, ContextTypes,
    TypeHandler, filters, Defaults,
)
from telegram.constants import ParseMode

import config


def setup_logging():
    os.makedirs(os.path.dirname(config.LOG_FILE), exist_ok=True)
    level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = RotatingFileHandler(
        config.LOG_FILE, maxBytes=5 * 1024 * 1024,
        backupCount=3, encoding="utf-8",
    )
    fh.setFormatter(fmt)
    fh.setLevel(level)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    ch.setLevel(level)
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(fh)
    root.addHandler(ch)
    for lib in ("httpx", "asyncssh", "telegram"):
        logging.getLogger(lib).setLevel(logging.WARNING)


setup_logging()
logger = logging.getLogger(__name__)

# ─── validate config ──────────────────────────────────────────────
if not config.TOKEN:
    logger.error("BOT_TOKEN is not set! Check your .env file.")
    sys.exit(1)
if not config.ADMIN_IDS:
    logger.error("ADMIN_IDS is not set! Check your .env file.")
    sys.exit(1)

from database.db import init_db_sync, is_banned as db_is_banned
from services.channel_check import ensure_default_settings, load_settings
from services import ssh_manager
from handlers import start as h_start
from handlers import help as h_help
from handlers import fast_ssh as h_fast
from handlers import my_hosts as h_hosts
from handlers import terminal as h_term
from handlers import admin as h_admin
from handlers import sftp as h_sftp
from handlers.stats import stats_reporter

# ─── stats reporter (Hpanel compatible) ──────────────────────────
_msg_history = []


async def maintenance_ban_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Middleware: maintenance mode and ban check"""
    if not update.effective_user:
        return

    uid = update.effective_user.id
    if uid in config.ADMIN_IDS:
        return  # Admin always has access

    cfg = load_settings()
    if cfg.get("maintenance", False):
        if update.message:
            await update.message.reply_text(
                "🔧 Bot is under maintenance. Please try again later."
            )
        elif update.callback_query:
            await update.callback_query.answer("🔧 Under maintenance.", show_alert=True)
        from telegram.ext import ApplicationHandlerStop
        raise ApplicationHandlerStop()

    if await db_is_banned(uid):
        if update.message:
            await update.message.reply_text("🚫 You have been banned from this bot.")
        elif update.callback_query:
            await update.callback_query.answer("🚫 You are banned.", show_alert=True)
        from telegram.ext import ApplicationHandlerStop
        raise ApplicationHandlerStop()


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    from telegram.ext import ApplicationHandlerStop
    if isinstance(context.error, ApplicationHandlerStop):
        return
    logger.error("Exception:", exc_info=context.error)
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text("⚠️ An error occurred. Please try again.")
    except Exception:
        pass


async def post_init(app: Application) -> None:
    logger.info("Initializing ssh-bot-Robexia v1.0...")
    mgr = ssh_manager.init_manager(app.bot)
    await mgr.start_watchdog()
    asyncio.create_task(stats_reporter())

    from telegram import BotCommand
    await app.bot.set_my_commands([
        BotCommand("start", "Back to main panel"),
        BotCommand("help", "Help & Guide"),
        BotCommand("fast_ssh", "Quick SSH connection"),
        BotCommand("my_hosts", "Saved servers"),
        BotCommand("close", "Close current session"),
        BotCommand("wait", "Background session"),
    ])
    logger.info("Bot ready.")


async def post_shutdown(app: Application) -> None:
    logger.info("Shutting down...")
    try:
        await ssh_manager.get_manager().shutdown()
    except Exception:
        pass


def main() -> None:
    logger.info(f"Starting ssh-bot-Robexia v1.0")
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    init_db_sync()
    ensure_default_settings()

    app = (
        ApplicationBuilder()
        .token(config.TOKEN)
        .defaults(Defaults(parse_mode=ParseMode.HTML))
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Middleware
    app.add_handler(TypeHandler(Update, maintenance_ban_middleware), group=-1)
    app.add_error_handler(error_handler)

    # /start
    app.add_handler(CommandHandler("start", h_start.start_command))
    app.add_handler(CallbackQueryHandler(h_start.check_join_callback, pattern=r"^check_join$"))

    # /help
    app.add_handler(CommandHandler("help", h_help.help_command))
    app.add_handler(MessageHandler(filters.Regex(r"^❓ راهنما$"), h_help.help_command))

    # /admin
    app.add_handler(h_admin.build_admin_handler())

    # fast_ssh
    app.add_handler(h_fast.build_fast_ssh_handler())

    # SFTP delete callback
    app.add_handler(CallbackQueryHandler(h_sftp.sftp_delete_callback, pattern=r"^sftp_del:"))

    # my_hosts
    for h in h_hosts.build_my_hosts_command_handler():
        app.add_handler(h)
    app.add_handler(h_hosts.build_add_host_handler())
    app.add_handler(h_hosts.build_edit_host_handler())
    app.add_handler(CallbackQueryHandler(
        h_hosts.hosts_callback,
        pattern=r"^(host_list|host_view:|host_connect:|host_delete:|host_delete_confirm:|host_edit:)",
    ))

    # /close, /wait
    app.add_handler(CommandHandler("close", h_term.close_command))
    app.add_handler(CommandHandler("wait", h_term.wait_command))

    # File upload → SFTP
    app.add_handler(MessageHandler(filters.Document.ALL, h_term.document_handler))

    # Text messages → terminal
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        h_term.terminal_message_handler,
    ))

    logger.info("Polling started...")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    from telegram.ext import ApplicationHandlerStop
    main()
