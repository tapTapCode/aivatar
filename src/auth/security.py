from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from urllib.parse import urlparse

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

PASSWORD_HASHER = PasswordHasher()
DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash("not-a-real-password")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value: str) -> str:
    email = value.strip().casefold()
    if len(email) > 320 or not EMAIL_PATTERN.fullmatch(email):
        raise ValueError("Enter a valid email address.")
    return email


def validate_password(value: str) -> str:
    if len(value) < 12:
        raise ValueError("Password must be at least 12 characters.")
    if len(value) > 256:
        raise ValueError("Password is too long.")
    return value


def hash_password(value: str) -> str:
    return PASSWORD_HASHER.hash(validate_password(value))


def verify_password(password_hash: str | None, candidate: str) -> bool:
    target = password_hash or DUMMY_PASSWORD_HASH
    try:
        valid = PASSWORD_HASHER.verify(target, candidate)
    except (InvalidHashError, VerifyMismatchError):
        valid = False
    return valid and password_hash is not None


def random_token(bytes_count: int = 32) -> str:
    return secrets.token_urlsafe(bytes_count)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_match(candidate: str, expected_hash: str) -> bool:
    return hmac.compare_digest(token_hash(candidate), expected_hash)


def safe_next_path(value: str | None) -> str:
    if not value:
        return "/"
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or not value.startswith("/") or value.startswith("//"):
        return "/"
    return value[:500]


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
