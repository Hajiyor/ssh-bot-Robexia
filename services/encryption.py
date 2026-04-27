"""
ماژول رمزنگاری AES-256-GCM برای ذخیره امن رمزها و کلیدهای SSH.

استراتژی:
- یک master_key در app_settings ذخیره می‌شود (بار اول اجرا ساخته می‌شود).
- برای هر کاربر، کلید مشتق شده از master_key + user_id محاسبه می‌شود (HKDF).
- بدین ترتیب حتی اگر کسی به دیتابیس دسترسی پیدا کند، بدون master_key نمی‌تواند
  رمزها را باز کند.
"""

import os
import base64
import logging
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

from database import db

logger = logging.getLogger(__name__)

_MASTER_KEY_CACHE: Optional[bytes] = None
SETTING_KEY = "master_encryption_key"


async def _get_master_key() -> bytes:
    """
    دریافت master_key از دیتابیس. اگر وجود نداشت، یک کلید 32 بایتی تصادفی می‌سازد.
    """
    global _MASTER_KEY_CACHE
    if _MASTER_KEY_CACHE is not None:
        return _MASTER_KEY_CACHE

    stored = await db.get_setting(SETTING_KEY)
    if stored:
        _MASTER_KEY_CACHE = base64.b64decode(stored)
        return _MASTER_KEY_CACHE

    # ساخت کلید جدید
    new_key = os.urandom(32)
    await db.set_setting(SETTING_KEY, base64.b64encode(new_key).decode())
    _MASTER_KEY_CACHE = new_key
    logger.info("New master encryption key generated and stored.")
    return new_key


async def _derive_user_key(user_id: int) -> bytes:
    """مشتق کردن کلید اختصاصی کاربر از master_key با استفاده از HKDF"""
    master = await _get_master_key()
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=str(user_id).encode(),
        info=b"ssh-bot-user-key",
    )
    return hkdf.derive(master)


async def encrypt(user_id: int, plaintext: str) -> bytes:
    """
    رمزنگاری یک رشته برای یک کاربر مشخص.
    خروجی: nonce (12 بایت) + ciphertext + tag
    """
    if plaintext is None:
        return None
    key = await _derive_user_key(user_id)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return nonce + ct


async def decrypt(user_id: int, data: bytes) -> Optional[str]:
    """
    رمزگشایی داده رمزنگاری شده برای یک کاربر مشخص.
    در صورت خطا None برمی‌گرداند.
    """
    if not data:
        return None
    try:
        key = await _derive_user_key(user_id)
        aesgcm = AESGCM(key)
        nonce = data[:12]
        ct = data[12:]
        pt = aesgcm.decrypt(nonce, ct, None)
        return pt.decode("utf-8")
    except Exception as e:
        logger.error(f"Decryption failed for user {user_id}: {e}")
        return None
