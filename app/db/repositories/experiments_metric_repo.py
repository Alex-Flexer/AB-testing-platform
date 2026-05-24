from __future__ import annotations

from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models.experiment import ExperimentMetric


class ExperimentMetricRepository:
    @staticmethod
    async def get_link(
        session: AsyncSession,
        *,
        experiment_id: UUID,
        metric_id: UUID,
    ) -> Optional[ExperimentMetric]:
        res = await session.execute(
            select(ExperimentMetric)
            .where(
                ExperimentMetric.experiment_id == experiment_id,
                ExperimentMetric.metric_id == metric_id,
            )
            .options(selectinload(ExperimentMetric.metric))
        )
        return res.scalar_one_or_none()

    @staticmethod
    async def list_links(
        session: AsyncSession,
        *,
        experiment_id: UUID,
        offset: int = 0,
        limit: int = 200,
    ) -> Sequence[ExperimentMetric]:
        q = (
            select(ExperimentMetric)
            .where(ExperimentMetric.experiment_id == experiment_id)
            .options(selectinload(ExperimentMetric.metric))
            .order_by(ExperimentMetric.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        res = await session.execute(q)
        return res.scalars().all()

    @staticmethod
    async def count_links(session: AsyncSession, *, experiment_id: UUID) -> int:
        res = await session.execute(
            select(func.count(ExperimentMetric.id)).where(
                ExperimentMetric.experiment_id == experiment_id)
        )
        return int(res.scalar_one())

    @staticmethod
    async def create_link(session: AsyncSession, link: ExperimentMetric) -> ExperimentMetric:
        session.add(link)
        await session.flush()
        await session.refresh(link)
        return link

    @staticmethod
    async def update_role(
        session: AsyncSession,
        link: ExperimentMetric,
        *,
        role: str,
    ) -> ExperimentMetric:
        link.role = role
        session.add(link)
        await session.flush()
        await session.refresh(link)
        return link

    @staticmethod
    async def delete_link(
        session: AsyncSession,
        *,
        experiment_id: UUID,
        metric_id: UUID,
    ) -> bool:
        res = await session.execute(
            delete(ExperimentMetric).where(
                ExperimentMetric.experiment_id == experiment_id,
                ExperimentMetric.metric_id == metric_id,
            )
        )
        return bool(res.rowcount)
