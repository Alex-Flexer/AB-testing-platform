import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import JWTError, jwt

from core.config import settings
from exceptions.app_exceptions import InvalidCredentials, AppException


def create_access_token(
    *,
    subject: str,
    expires_minutes: Optional[int] = None,
    extra_claims: Optional[dict[str, Any]] = None,
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=(expires_minutes or settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }

    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_aud": False},
        )
    except JWTError:
        raise InvalidCredentials()

    if payload.get("type") != "access":
        raise InvalidCredentials()

    sub = payload.get("sub")
    if not sub:
        raise InvalidCredentials("token missing subject")

    return payload


def hash_password(password: str) -> str:
    if not password or not isinstance(password, str):
        raise AppException("password must be non-empty string")

    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    if not password or not password_hash:
        return False

    return bcrypt.checkpw(password.encode(), password_hash.encode())
