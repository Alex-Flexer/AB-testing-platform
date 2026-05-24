from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from db.enums import UserRole
from db.repositories.users_repo import UserRepository
from exceptions.app_exceptions import InvalidCredentials, Forbidden
from core.security import decode_access_token


bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db),
):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise InvalidCredentials("missing bearer token")

    token = credentials.credentials
    payload = decode_access_token(token)

    try:
        user_id = UUID(payload["sub"])
    except Exception:
        raise InvalidCredentials("invalid token subject")

    user = await UserRepository.get_by_id(session, user_id)
    if user is None:
        raise InvalidCredentials("user not found")

    if not user.is_active:
        raise Forbidden("user is inactive")

    return user


def require_roles(*roles: UserRole):
    async def _dep(user=Depends(get_current_user)):
        if user.role not in roles:
            raise Forbidden(f"required role: {', '.join(r.value for r in roles)}")
        return user
    return _dep


async def require_admin(user=Depends(get_current_user)):
    if user.role != UserRole.ADMIN:
        raise Forbidden()
    return user
