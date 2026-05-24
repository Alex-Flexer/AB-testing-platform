from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.enums import FlagType
from db.repositories.feature_flags_repo import FeatureFlagRepository
from exceptions.app_exceptions import (
    AppException,
    UnprocessableEntity,
)
from exceptions.app_exceptions import FeatureFlagNotFound, FeatureFlagKeyAlreadyExists
from schemas.feature_flag import FeatureFlagCreate, FeatureFlagUpdate


_NUM_RE = re.compile(r"^[+-]?\d+(\.\d+)?$")


class FeatureFlagService:
    def __init__(self):
        self.repo = FeatureFlagRepository

    @staticmethod
    def _validate_default_value_for_type(flag_type: FlagType, default_value: str) -> None:
        if flag_type == FlagType.BOOL:
            if default_value not in ("true", "false"):
                raise UnprocessableEntity("default_value must be boolean for type=bool")

        elif flag_type == FlagType.NUMBER:
            if not _NUM_RE.match(default_value):
                raise UnprocessableEntity("default_value must be number for type=number")

        else:
            if not default_value:
                raise UnprocessableEntity("default_value must not be empty for type=string")

    async def create_flag(self, session: AsyncSession, data: FeatureFlagCreate):
        existing = await self.repo.get_by_key(session, data.key)
        if existing is not None:
            raise FeatureFlagKeyAlreadyExists()

        try:
            flag = await self.repo.create(
                session,
                key=data.key,
                type=data.type,
                default_value=str(data.default_value),
                description=str(data.description) if data.description is not None else None,
            )
            await session.commit()
            return flag

        except IntegrityError:
            await session.rollback()
            raise FeatureFlagKeyAlreadyExists()

        except Exception:
            await session.rollback()
            raise AppException()

    async def get_flag(self, session: AsyncSession, flag_id: UUID):
        flag = await self.repo.get_by_id(session, flag_id)
        if flag is None:
            raise FeatureFlagNotFound()
        return flag

    async def list_flags(self, session: AsyncSession, *, offset: int = 0, limit: int = 50):
        if offset < 0:
            raise UnprocessableEntity("offset must be >= 0")

        if limit <= 0 or limit > 200:
            raise UnprocessableEntity("limit must be in range 1..200")

        items = await self.repo.list(session, offset=offset, limit=limit)
        total = await self.repo.count(session)

        return items, total

    async def update_flag(self, session: AsyncSession, flag_id: UUID, data: FeatureFlagUpdate):
        flag = await self.repo.get_by_id(session, flag_id)
        if flag is None:
            raise FeatureFlagNotFound()

        new_default = str(data.default_value)
        self._validate_default_value_for_type(flag.type, new_default)

        try:
            flag = await self.repo.update_default_value(session, flag, default_value=new_default)
            await session.commit()
            return flag

        except Exception:
            await session.rollback()
            raise AppException()

    async def delete_flag(self, session: AsyncSession, flag_id: UUID):
        try:
            deleted = await self.repo.delete_by_id(session, flag_id)
            await session.commit()

        except Exception:
            await session.rollback()
            raise AppException()

        if not deleted:
            raise FeatureFlagNotFound()
