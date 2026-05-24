from __future__ import annotations

from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import select, func, delete
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.experiment import Experiment
from db.models.variant import Variant


class ExperimentRepository:
    @staticmethod
    async def get_by_id(session: AsyncSession, experiment_id: UUID) -> Optional[Experiment]:
        q = (
            select(Experiment)
            .where(Experiment.id == experiment_id)
            .options(selectinload(Experiment.variants))
        )
        res = await session.execute(q)
        return res.scalar_one_or_none()

    @staticmethod
    async def list(
        session: AsyncSession,
        offset: int = 0,
        limit: int = 50,
        status: Optional[str] = None,
    ) -> Sequence[Experiment]:
        q = select(Experiment).options(
            selectinload(Experiment.variants)
        ).offset(offset).limit(limit)

        if status is not None:
            q = q.where(Experiment.status == status)

        res = await session.execute(q.order_by(Experiment.created_at.desc()))
        return res.scalars().all()

    @staticmethod
    async def count(session: AsyncSession, *, status: Optional[str] = None) -> int:
        q = select(func.count(Experiment.id))
        if status is not None:
            q = q.where(Experiment.status == status)

        res = await session.execute(q)
        return int(res.scalar_one())

    @staticmethod
    async def create(session: AsyncSession, exp: Experiment) -> Experiment:
        session.add(exp)
        await session.flush()
        return exp

    @staticmethod
    async def add_variants(session: AsyncSession, experiment_id: UUID, variants: list[Variant]) -> None:
        for v in variants:
            v.experiment_id = experiment_id
            session.add(v)

        await session.flush()

    @staticmethod
    async def delete_by_id(session: AsyncSession, experiment_id: UUID) -> bool:
        res = await session.execute(delete(Experiment).where(Experiment.id == experiment_id))
        return res.rowcount > 0

    @staticmethod
    async def get_variants(session: AsyncSession, experiment_id: UUID) -> list[Variant]:
        res = await session.execute(
            select(Variant)
            .where(Variant.experiment_id == experiment_id)
            .order_by(Variant.name.asc())
        )
        return list(res.scalars().all())
