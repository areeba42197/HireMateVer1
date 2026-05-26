import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

from .config import SECRET_KEY


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return base64.b64encode(salt + digest).decode("ascii")


def verify_password(password: str, stored: str) -> bool:
    raw = base64.b64decode(stored.encode("ascii"))
    salt, old_digest = raw[:16], raw[16:]
    new_digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return hmac.compare_digest(old_digest, new_digest)


def utc_now():
    return datetime.now(timezone.utc)


def iso_after(hours: int) -> str:
    return (utc_now() + timedelta(hours=hours)).isoformat()


def new_token() -> str:
    raw = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii").rstrip("=")
    sig = hmac.new(SECRET_KEY.encode("utf-8"), raw.encode("ascii"), hashlib.sha256).hexdigest()[:24]
    return f"{raw}.{sig}"


def token_signature_ok(token: str) -> bool:
    if "." not in token:
        return False
    raw, sig = token.rsplit(".", 1)
    expected = hmac.new(SECRET_KEY.encode("utf-8"), raw.encode("ascii"), hashlib.sha256).hexdigest()[:24]
    return hmac.compare_digest(sig, expected)


def _keystream(length: int) -> bytes:
    key = SECRET_KEY.encode("utf-8")
    out = bytearray()
    counter = 0
    while len(out) < length:
        counter += 1
        out.extend(hmac.new(key, str(counter).encode("ascii"), hashlib.sha256).digest())
    return bytes(out[:length])


def protect_text(value: str) -> str:
    raw = value.encode("utf-8")
    stream = _keystream(len(raw))
    cipher = bytes(a ^ b for a, b in zip(raw, stream))
    return base64.urlsafe_b64encode(cipher).decode("ascii")


def reveal_text(value: str) -> str:
    cipher = base64.urlsafe_b64decode(value.encode("ascii"))
    stream = _keystream(len(cipher))
    raw = bytes(a ^ b for a, b in zip(cipher, stream))
    return raw.decode("utf-8")
