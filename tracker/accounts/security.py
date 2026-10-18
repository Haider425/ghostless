"""Passwords and tokens.

Passwords are hashed with Argon2id (the OWASP recommendation). Session and
email tokens are random 256-bit values; only their SHA-256 is stored, so the
database alone can't be used to log in.
"""

from __future__ import annotations

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()
# compared against when the email doesn't exist, so a login takes the same
# time either way and can't be used to discover which emails have accounts
_DUMMY_HASH = _hasher.hash("not a real password")

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 256


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def password_problem(password: str, email: str = "") -> str | None:
    """Why a password isn't acceptable, or None."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Use at least {MIN_PASSWORD_LENGTH} characters."
    if len(password) > MAX_PASSWORD_LENGTH:
        return "That password is too long."
    if email and password.lower() == email.lower():
        return "Don't use your email address as your password."
    if len(set(password)) < 4:
        return "That password is too easy to guess."
    return None


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
