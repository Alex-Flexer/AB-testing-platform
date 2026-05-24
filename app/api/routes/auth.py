from fastapi import APIRouter, Depends

from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from db.repositories.users_repo import UserRepository

from schemas.auth import TokenRequest, TokenResponse

from core.security import create_access_token, verify_password

from exceptions.app_exceptions import UserNotFound, Forbidden, InvalidCredentials


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def issue_token(data: TokenRequest, session: AsyncSession = Depends(get_db)):
    user = await UserRepository.get_by_email(session, data.email.strip().lower())

    if user is None:
        raise UserNotFound()

    if not user.is_active:
        raise Forbidden("user is inactive")

    if not verify_password(data.password, user.password_hash):
        raise InvalidCredentials("invalid password or email")

    token = create_access_token(
        subject=str(user.id),
        extra_claims={"role": user.role.value},
    )

    return TokenResponse(access_token=token)
