from __future__ import annotations

import base64
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


KEY_ENV = "SHADOW_TEXT_KEY"
SALT = b"shadow-text-v1"


def encrypt_text(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_text(token: str) -> str:
    return _fernet().decrypt(token.encode("ascii")).decode("utf-8")


def require_key() -> str:
    value = os.environ.get(KEY_ENV)
    if not value:
        raise RuntimeError(
            f"{KEY_ENV} non e impostata. Imposta una password/chiave locale prima "
            "di censurare o ripristinare: $env:SHADOW_TEXT_KEY=\"...\""
        )
    return value


def _fernet() -> Fernet:
    secret = require_key().encode("utf-8")
    if _looks_like_fernet_key(secret):
        return Fernet(secret)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SALT,
        iterations=390000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(secret))
    return Fernet(key)


def _looks_like_fernet_key(value: bytes) -> bool:
    if len(value) != 44:
        return False
    try:
        base64.urlsafe_b64decode(value)
    except Exception:
        return False
    return True
