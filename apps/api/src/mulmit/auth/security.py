"""Password hashing (Argon2id) and session tokens (JWT in an httpOnly cookie)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from mulmit.settings import Settings

_hasher = PasswordHasher()
COOKIE_NAME = "mulmit_session"
_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_token(settings: Settings, *, user_id: int, org_id: int, staff: bool) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "org": org_id,
        "staff": staff,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_ttl_minutes)).timestamp()),
        "iss": "mulmit",
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=_ALGORITHM)


def decode_token(settings: Settings, token: str) -> dict[str, Any]:
    decoded: dict[str, Any] = jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=[_ALGORITHM],
        issuer="mulmit",
        options={"require": ["exp", "sub", "iss"]},
    )
    return decoded
