from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.enums import UserRole
from db.repositories.users_repo import UserRepository
from schemas.user import UserCreate, UserUpdate
from exceptions.app_exceptions import (
    UserNotFound,
    AppException,
    EmailAlreadyExists,
    UnprocessableEntity,
)


class UserService:
    def __init__(self):
        self.repo = UserRepository

    @staticmethod
    def _is_role_admin(role: UserRole) -> bool:
        return role == UserRole.ADMIN

    async def create_user(self, session: AsyncSession, data: UserCreate):
        existing = await self.repo.get_by_email(session, data.email)
        if existing is not None:
            raise EmailAlreadyExists()

        try:
            user = await self.repo.create(
                session,
                email=data.email,
                role=data.role,
                is_active=bool(data.is_active),
                password=data.password
            )
            await session.commit()
            return user

        except IntegrityError:
            await session.rollback()
            raise EmailAlreadyExists()

        except Exception:
            await session.rollback()
            raise AppException()

    async def get_user(self, session: AsyncSession, user_id: UUID):
        user = await self.repo.get_by_id(session, user_id)
        if user is None:
            raise UserNotFound()

        return user

    async def get_user_by_email(self, session: AsyncSession, email: str):
        user = await self.repo.get_by_email(session, email)
        if user is None:
            raise UserNotFound()

        return user

    async def list_users(
        self,
        session: AsyncSession,
        *,
        offset: int = 0,
        limit: int = 50
    ):
        if offset < 0:
            raise UnprocessableEntity("offset must be >= 0")

        if limit <= 0 or limit > 200:
            raise UnprocessableEntity("limit must be in range 1..200")

        items = await self.repo.list(session, offset=offset, limit=limit)
        total = await self.repo.count(session)

        return items, total

    async def update_user(self, session: AsyncSession, user_id: UUID, data: UserUpdate):
        user = await self.repo.get_by_id(session, user_id)

        if user is None:
            raise UserNotFound()

        new_email = data.email if data.email is not None else None
        new_role = data.role if data.role is not None else None
        new_active = bool(data.is_active) if data.is_active is not None else None

        # If email changes -> ensure uniqueness
        if new_email is not None and new_email != user.email:
            other = await self.repo.get_by_email(session, new_email)
            if other is not None and other.id != user.id:
                raise EmailAlreadyExists()

        try:
            user = await self.repo.update(
                session,
                user,
                email=new_email,
                role=new_role,
                is_active=new_active,
            )
            await session.commit()
            return user

        except IntegrityError:
            await session.rollback()
            raise EmailAlreadyExists()

        except Exception:
            await session.rollback()
            raise AppException()

    async def delete_user(self, session: AsyncSession, user_id: UUID):
        try:
            deleted = await self.repo.delete_by_id(session, user_id)
            if not deleted:
                raise UserNotFound()

            await session.commit()
            return True
        except Exception:
            await session.rollback()
            raise AppException()

    async def deactivate_user(self, session: AsyncSession, user_id: UUID):
        """
        Soft delete
        """
        try:
            user = await self.repo.get_by_id(session, user_id)
            if user is None:
                raise UserNotFound()

            self.repo.update(session, user, is_active=False)
            await session.commit()
            return True

        except Exception:
            await session.rollback()
            raise AppException()
