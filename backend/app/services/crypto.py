"""Encryption at rest for uploaded documents and extracted identifiers (Fernet / AES-128-CBC + HMAC)."""
import base64
import hashlib
import json
from functools import lru_cache

from cryptography.fernet import Fernet

from ..config import get_settings


@lru_cache
def _fernet() -> Fernet:
    s = get_settings()
    key = s.encryption_key.encode() if s.encryption_key else base64.urlsafe_b64encode(hashlib.sha256(s.jwt_secret.encode()).digest())
    return Fernet(key)


def encrypt_bytes(data: bytes) -> bytes:
    return _fernet().encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    return _fernet().decrypt(token)


def encrypt_json(obj) -> dict:
    return {"enc": _fernet().encrypt(json.dumps(obj, ensure_ascii=False).encode()).decode()}


def decrypt_json(blob: dict):
    if not blob or "enc" not in blob:
        return {}
    return json.loads(_fernet().decrypt(blob["enc"].encode()).decode())
