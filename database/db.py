"""
database/db.py - Schema و CRUD

جداول:
- users: کاربران (user_id, username, first_name, first_seen, last_seen, message_count, is_banned)
- hosts: سرورهای ذخیره شده (تا 5 عدد برای هر کاربر)
- app_settings: تنظیمات داخلی (AES key، متن‌های قابل تغییر، ...)
- ssh_logs: لاگ اتصالات SSH برای آمار
"""

import aiosqlite
import sqlite3
import logging
from datetime import datetime, date
from typing import Optional, List, Dict, Any

import config

logger = logging.getLogger(__name__)
MAX_HOSTS_PER_USER = 5


def init_db_sync():
    """راه‌اندازی اولیه دیتابیس (sync - در startup صدا زده می‌شود)"""
    conn = sqlite3.connect(config.DB_PATH)
    try:
        c = conn.cursor()

        # جدول کاربران
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id      INTEGER PRIMARY KEY,
                username     TEXT,
                first_name   TEXT,
                first_seen   DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_seen    DATETIME DEFAULT CURRENT_TIMESTAMP,
                message_count INTEGER DEFAULT 0,
                is_banned    INTEGER DEFAULT 0
            )
        """)

        # migration: اضافه کردن ستون‌های جدید اگر نبودند
        for col in [
            "ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0",
        ]:
            try:
                c.execute(col)
            except sqlite3.OperationalError:
                pass

        # جدول سرورهای ذخیره شده
        c.execute("""
            CREATE TABLE IF NOT EXISTS hosts (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id            INTEGER NOT NULL,
                name               TEXT NOT NULL,
                host               TEXT NOT NULL,
                port               INTEGER DEFAULT 22,
                username           TEXT NOT NULL,
                auth_type          TEXT NOT NULL CHECK(auth_type IN ('password','key')),
                password_enc       BLOB,
                key_enc            BLOB,
                key_passphrase_enc BLOB,
                created_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_hosts_user ON hosts(user_id)")

        # جدول تنظیمات داخلی
        c.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # جدول لاگ اتصالات SSH
        c.execute("""
            CREATE TABLE IF NOT EXISTS ssh_logs (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id        INTEGER NOT NULL,
                host           TEXT NOT NULL,
                connected_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                disconnected_at DATETIME,
                success        INTEGER DEFAULT 1
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_logs_user ON ssh_logs(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_logs_date ON ssh_logs(connected_at)")

        conn.commit()
        logger.info("Database initialized.")
    finally:
        conn.close()


# ─── Users ───────────────────────────────────────────────────────

async def save_user(user_id: int, username: Optional[str] = None,
                    first_name: Optional[str] = None) -> None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, first_name, last_seen, message_count)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, 1)
            ON CONFLICT(user_id) DO UPDATE SET
                username      = excluded.username,
                first_name    = excluded.first_name,
                last_seen     = CURRENT_TIMESTAMP,
                message_count = message_count + 1
        """, (user_id, username, first_name))
        await db.commit()


async def is_banned(user_id: int) -> bool:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            "SELECT is_banned FROM users WHERE user_id=?", (user_id,)
        )
        row = await cur.fetchone()
        return bool(row and row[0])


async def ban_user(user_id: int) -> None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (user_id,))
        await db.commit()


async def unban_user(user_id: int) -> None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (user_id,))
        await db.commit()


async def get_user_info(user_id: int) -> Optional[Dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


# ─── Admin Stats ─────────────────────────────────────────────────

async def get_stats() -> Dict[str, Any]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        total_users  = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
        active_users = (await (await db.execute("SELECT COUNT(*) FROM users WHERE is_banned=0")).fetchone())[0]
        banned_users = (await (await db.execute("SELECT COUNT(*) FROM users WHERE is_banned=1")).fetchone())[0]
        total_hosts  = (await (await db.execute("SELECT COUNT(*) FROM hosts")).fetchone())[0]
        total_ssh    = (await (await db.execute("SELECT COUNT(*) FROM ssh_logs")).fetchone())[0]

        today = date.today().isoformat()
        today_users = (await (await db.execute(
            "SELECT COUNT(DISTINCT user_id) FROM users WHERE date(last_seen)=?", (today,)
        )).fetchone())[0]
        today_ssh = (await (await db.execute(
            "SELECT COUNT(*) FROM ssh_logs WHERE date(connected_at)=?", (today,)
        )).fetchone())[0]

    return {
        "total_users":  total_users,
        "active_users": active_users,
        "banned_users": banned_users,
        "total_hosts":  total_hosts,
        "total_ssh":    total_ssh,
        "today_users":  today_users,
        "today_ssh":    today_ssh,
    }


# ─── SSH Logs ────────────────────────────────────────────────────

async def log_ssh_connect(user_id: int, host: str) -> int:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO ssh_logs (user_id, host) VALUES (?, ?)", (user_id, host)
        )
        await db.commit()
        return cur.lastrowid


async def log_ssh_disconnect(log_id: int) -> None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE ssh_logs SET disconnected_at=CURRENT_TIMESTAMP WHERE id=?", (log_id,)
        )
        await db.commit()


# ─── Hosts ──────────────────────────────────────────────────────

async def get_user_hosts(user_id: int) -> List[Dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id,name,host,port,username,auth_type,created_at "
            "FROM hosts WHERE user_id=? ORDER BY created_at DESC", (user_id,)
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_host_by_id(host_id: int, user_id: int) -> Optional[Dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM hosts WHERE id=? AND user_id=?", (host_id, user_id)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def count_user_hosts(user_id: int) -> int:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM hosts WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else 0


async def add_host(user_id: int, name: str, host: str, port: int,
                   username: str, auth_type: str,
                   password_enc=None, key_enc=None,
                   key_passphrase_enc=None) -> Optional[int]:
    if await count_user_hosts(user_id) >= MAX_HOSTS_PER_USER:
        return None
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO hosts
            (user_id,name,host,port,username,auth_type,password_enc,key_enc,key_passphrase_enc)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (user_id, name, host, port, username, auth_type,
              password_enc, key_enc, key_passphrase_enc))
        await db.commit()
        return cur.lastrowid


async def update_host(host_id: int, user_id: int, **fields) -> bool:
    allowed = {'name','host','port','username','auth_type',
               'password_enc','key_enc','key_passphrase_enc'}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return False
    set_clause = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [host_id, user_id]
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            f"UPDATE hosts SET {set_clause} WHERE id=? AND user_id=?", vals
        )
        await db.commit()
        return cur.rowcount > 0


async def delete_host(host_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM hosts WHERE id=? AND user_id=?", (host_id, user_id)
        )
        await db.commit()
        return cur.rowcount > 0


# ─── App Settings ───────────────────────────────────────────────

async def get_setting(key: str) -> Optional[str]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            "SELECT value FROM app_settings WHERE key=?", (key,)
        )
        row = await cur.fetchone()
        return row[0] if row else None


async def set_setting(key: str, value: str) -> None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("""
            INSERT INTO app_settings (key,value) VALUES (?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (key, value))
        await db.commit()


# ─── SFTP Last Path ───────────────────────────────────────────────

async def get_sftp_last_path(user_id: int, host_id: int) -> str:
    val = await get_setting(f"sftp_path_{user_id}_{host_id}")
    return val or "."


async def save_sftp_last_path(user_id: int, host_id: int, path: str) -> None:
    await set_setting(f"sftp_path_{user_id}_{host_id}", path)


# ─── Last SSH Host ────────────────────────────────────────────────

async def get_last_host_id(user_id: int) -> Optional[int]:
    val = await get_setting(f"last_host_{user_id}")
    try:
        return int(val) if val else None
    except ValueError:
        return None


async def save_last_host_id(user_id: int, host_id: int) -> None:
    await set_setting(f"last_host_{user_id}", str(host_id))
