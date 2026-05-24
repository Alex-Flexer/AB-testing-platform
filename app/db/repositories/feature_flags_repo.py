from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy import func, select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.feature_flag import FeatureFlag
from db.models.experiment import Experiment

from db.enums import FlagType, ExperimentStatus


class FeatureFlagRepository:
    @staticmethod
    async def get_by_id(session: AsyncSession, flag_id: UUID) -> FeatureFlag | None:
        result = await session.execute(
            select(FeatureFlag).where(FeatureFlag.id == flag_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_key(session: AsyncSession, key: str) -> FeatureFlag | None:
        result = await session.execute(
            select(FeatureFlag).where(FeatureFlag.key == key)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list(
        session: AsyncSession,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[FeatureFlag]:
        result = await session.execute(
            select(FeatureFlag)
            .order_by(FeatureFlag.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return result.scalars().all()

    @staticmethod
    async def count(session: AsyncSession) -> int:
        result = await session.execute(select(func.count(FeatureFlag.id)))
        return int(result.scalar_one())

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        key: str,
        type: FlagType,
        default_value: str,
        description: str | None = None,
    ) -> FeatureFlag:
        flag = FeatureFlag(
            key=key,
            type=type,
            default_value=default_value,
            description=description,
        )
        session.add(flag)
        await session.flush()
        return flag

    @staticmethod
    async def update_default_value(
        session: AsyncSession,
        flag: FeatureFlag,
        *,
        default_value: str,
    ) -> FeatureFlag:
        flag.default_value = default_value
        session.add(flag)
        await session.flush()
        return flag

    @staticmethod
    async def delete_by_id(session: AsyncSession, flag_id: UUID) -> bool:
        result = await session.execute(
            delete(FeatureFlag).where(FeatureFlag.id == flag_id)
        )
        return result.rowcount > 0

    @staticmethod
    async def get_active_experiment(
        session: AsyncSession,
        flag_id: UUID,
    ) -> Experiment | None:
        res = await session.execute(
            select(Experiment)
            .where(
                Experiment.feature_flag_id == flag_id,
                Experiment.status == ExperimentStatus.RUNNING,
            )
        )
        return res.scalar_one_or_none()
