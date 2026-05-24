# db/repositories/report_repo.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models.experiment import Experiment, ExperimentMetric
from db.models.metric import Metric
from db.models.event import Event


@dataclass
class EventRow:
    decision_id: UUID
    variant_id: UUID
    subject_id: str
    event_name: str
    occurred_at: datetime
    props: dict


class ReportRepository:
    # -------------------------
    # Experiment / Metrics
    # -------------------------

    @staticmethod
    async def get_experiment_with_variants(
        session: AsyncSession,
        experiment_id: UUID,
    ) -> Optional[Experiment]:
        q = (
            select(Experiment)
            .where(Experiment.id == experiment_id)
            .options(selectinload(Experiment.variants))
        )
        res = await session.execute(q)
        return res.scalar_one_or_none()

    @staticmethod
    async def get_metrics_for_experiment(
        session: AsyncSession,
        experiment_id: UUID,
    ) -> Sequence[Metric]:
        q = (
            select(Metric)
            .join(ExperimentMetric, ExperimentMetric.metric_id == Metric.id)
            .where(ExperimentMetric.experiment_id == experiment_id)
            .order_by(Metric.created_at.desc())
        )
        res = await session.execute(q)
        return res.scalars().all()

    @staticmethod
    async def get_metrics_by_keys(
        session: AsyncSession,
        keys: list[str],
    ) -> Sequence[Metric]:
        if not keys:
            return []
        q = select(Metric).where(Metric.key.in_(keys))
        res = await session.execute(q)
        return res.scalars().all()

    # -------------------------
    # Events
    # -------------------------

    @staticmethod
    async def fetch_events(
        session: AsyncSession,
        experiment_id: UUID,
        from_ts: datetime,
        to_ts: datetime,
        *,
        event_names: Optional[set[str]] = None,
    ) -> list[EventRow]:
        q = (
            select(
                Event.decision_id,
                Event.variant_id,
                Event.subject_id,
                Event.event_name,
                Event.occurred_at,
                Event.props,
            )
            .where(
                Event.experiment_id == experiment_id,
                Event.occurred_at >= from_ts,
                Event.occurred_at < to_ts,
            )
            .order_by(Event.occurred_at.asc())
        )

        if event_names:
            q = q.where(Event.event_name.in_(list(event_names)))

        res = await session.execute(q)
        rows = []
        for r in res.all():
            rows.append(
                EventRow(
                    decision_id=r[0],
                    variant_id=r[1],
                    subject_id=r[2],
                    event_name=r[3],
                    occurred_at=r[4],
                    props=r[5] or {},
                )
            )
        return rows

    @staticmethod
    async def fetch_exposures_decision_ids(
        session: AsyncSession,
        experiment_id: UUID,
        from_ts: datetime,
        to_ts: datetime,
        *,
        exposure_event_name: str = "exposure",
    ) -> set[UUID]:
        q = (
            select(Event.decision_id)
            .where(
                Event.experiment_id == experiment_id,
                Event.event_name == exposure_event_name,
                Event.occurred_at >= from_ts,
                Event.occurred_at < to_ts,
            )
            .distinct()
        )
        res = await session.execute(q)
        return set(res.scalars().all())
