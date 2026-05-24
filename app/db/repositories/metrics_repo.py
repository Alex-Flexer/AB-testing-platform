from __future__ import annotations

from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.metric import Metric


class MetricRepository:
    @staticmethod
    async def get_by_id(session: AsyncSession, metric_id: UUID) -> Optional[Metric]:
        res = await session.execute(select(Metric).where(Metric.id == metric_id))
        return res.scalar_one_or_none()

    @staticmethod
    async def get_by_key(session: AsyncSession, key: str) -> Optional[Metric]:
        res = await session.execute(select(Metric).where(Metric.key == key))
        return res.scalar_one_or_none()

    @staticmethod
    async def list(
        session: AsyncSession,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[Metric]:
        stmt = (
            select(Metric)
            .order_by(Metric.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        res = await session.execute(stmt)
        return res.scalars().all()

    @staticmethod
    async def count(session: AsyncSession) -> int:
        res = await session.execute(select(func.count(Metric.id)))
        return int(res.scalar_one())

    # ---------- Writes ----------

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        key: str,
        name: str,
        description: str | None,
        aggregation_type,
        numerator_event: str | None = None,
        denominator_event: str | None = None,
        field_path: str | None = None,
        requires_exposure: bool = False,
        created_by: UUID | None = None,
    ) -> Metric:
        m = Metric(
            key=key,
            name=name,
            description=description,
            aggregation_type=aggregation_type,
            numerator_event=numerator_event,
            denominator_event=denominator_event,
            field_path=field_path,
            requires_exposure=requires_exposure,
            created_by=created_by,
        )
        session.add(m)
        await session.flush()
        await session.refresh(m)
        return m

    @staticmethod
    async def update(
        session: AsyncSession,
        metric: Metric,
        *,
        name: str | None = None,
        description: str | None = None,
        aggregation_type=None,
        numerator_event: str | None = None,
        denominator_event: str | None = None,
        field_path: str | None = None,
        requires_exposure: bool | None = None,
    ) -> Metric:
        if name is not None:
            metric.name = name
        if description is not None:
            metric.description = description

        if aggregation_type is not None:
            metric.aggregation_type = aggregation_type

        metric.numerator_event = numerator_event
        metric.denominator_event = denominator_event
        metric.field_path = field_path

        if requires_exposure is not None:
            metric.requires_exposure = requires_exposure

        session.add(metric)
        await session.flush()
        await session.refresh(metric)
        return metric

    @staticmethod
    async def delete_by_id(session: AsyncSession, metric_id: UUID) -> bool:
        res = await session.execute(delete(Metric).where(Metric.id == metric_id))
        return bool(res.rowcount)
