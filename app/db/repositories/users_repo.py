from __future__ import annotations

from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.user import User
from core.security import hash_password


class UserRepository:
    @staticmethod
    async def get_by_id(session: AsyncSession, user_id: UUID) -> Optional[User]:
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_email(session: AsyncSession, email: str) -> Optional[User]:
        result = await session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list(
        session: AsyncSession,
        *,
        offset: int = 0,
        limit: int = 50
    ) -> Sequence[User]:
        stmt = select(User).order_by(User.created_at.desc())

        stmt = stmt.offset(offset).limit(limit)

        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def count(session: AsyncSession, *, email: Optional[str] = None) -> int:
        stmt = select(func.count()).select_from(User)
        if email:
            stmt = stmt.where(User.email == email)

        result = await session.execute(stmt)
        return int(result.scalar_one())

    # ---------- Writes ----------

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        email: str,
        role: str,
        is_active: bool,
        password: str
    ) -> User:
        password_hash = hash_password(password)
        user = User(email=email, role=role, is_active=is_active, password_hash=password_hash)
        session.add(user)

        await session.flush()
        await session.refresh(user)
        return user

    @staticmethod
    async def update(
        session: AsyncSession,
        user: User,
        *,
        email: Optional[str] = None,
        role=None,
        is_active: Optional[bool] = None,
    ) -> User:
        # apply patch
        if email is not None:
            user.email = email

        if role is not None:
            user.role = role

        if is_active is not None:
            user.is_active = is_active

        session.add(user)
        await session.flush()
        await session.refresh(user)
        return user

    @staticmethod
    async def delete_by_id(session: AsyncSession, user_id: UUID) -> bool:
        result = await session.execute(
            delete(User).where(User.id == user_id)
        )
        return bool(result.rowcount)
