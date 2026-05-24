from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.guardrail import Guardrail
from db.models.guardrail_trigger import GuardrailTrigger
from db.models.metric import Metric
from db.models.experiment import ExperimentMetric


class GuardrailRepository:
    # ----------------
    # Guardrails CRUD
    # ----------------

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        experiment_id: UUID,
        metric_id: UUID,
        comparison_operator,
        threshold: float,
        window_minutes: int,
        action,
        enabled: bool = True,
    ) -> Guardrail:
        g = Guardrail(
            experiment_id=experiment_id,
            metric_id=metric_id,
            comparison_operator=comparison_operator,
            threshold=float(threshold),
            window_minutes=float(window_minutes),
            action=action,
            enabled=bool(enabled),
            created_at=datetime.utcnow(),
        )
        session.add(g)
        await session.flush()
        await session.refresh(g)
        return g

    @staticmethod
    async def get_by_id(session: AsyncSession, guardrail_id: UUID) -> Optional[Guardrail]:
        q = (
            select(Guardrail)
            .where(Guardrail.id == guardrail_id)
            .options(selectinload(Guardrail.metric))
        )
        res = await session.execute(q)
        return res.scalar_one_or_none()

    @staticmethod
    async def list_by_experiment(
        session: AsyncSession,
        *,
        experiment_id: UUID,
        offset: int = 0,
        limit: int = 50,
        enabled_only: bool = False,
    ) -> Sequence[Guardrail]:
        q = (
            select(Guardrail)
            .where(Guardrail.experiment_id == experiment_id)
            .options(selectinload(Guardrail.metric))
        )

        if enabled_only:
            q = q.where(Guardrail.enabled.is_(True))

        q = q.order_by(Guardrail.created_at.desc()).offset(offset).limit(limit)

        res = await session.execute(q)
        return res.scalars().all()

    @staticmethod
    async def count_by_experiment(
        session: AsyncSession,
        *,
        experiment_id: UUID,
        enabled_only: bool = False,
    ) -> int:
        q = select(func.count(Guardrail.id)).where(Guardrail.experiment_id == experiment_id)
        if enabled_only:
            q = q.where(Guardrail.enabled.is_(True))
        res = await session.execute(q)
        return int(res.scalar_one())

    @staticmethod
    async def delete_by_id(session: AsyncSession, guardrail_id: UUID) -> bool:
        res = await session.execute(delete(Guardrail).where(Guardrail.id == guardrail_id))
        return (res.rowcount or 0) > 0

    @staticmethod
    async def update(
        session: AsyncSession,
        guardrail: Guardrail,
        *,
        threshold: float | None = None,
        window_minutes: int | None = None,
        comparison_operator=None,
        action=None,
        enabled: bool | None = None,
    ) -> Guardrail:
        if threshold is not None:
            guardrail.threshold = float(threshold)
        if window_minutes is not None:
            guardrail.window_minutes = float(window_minutes)
        if comparison_operator is not None:
            guardrail.comparison_operator = comparison_operator
        if action is not None:
            guardrail.action = action
        if enabled is not None:
            guardrail.enabled = bool(enabled)

        session.add(guardrail)
        await session.flush()
        await session.refresh(guardrail)
        return guardrail

    # ----------------
    # Metric & linking
    # ----------------

    @staticmethod
    async def get_metric_by_key(session: AsyncSession, metric_key: str) -> Optional[Metric]:
        res = await session.execute(select(Metric).where(Metric.key == metric_key))
        return res.scalar_one_or_none()

    @staticmethod
    async def is_metric_linked_to_experiment(
        session: AsyncSession,
        *,
        experiment_id: UUID,
        metric_id: UUID,
    ) -> bool:
        res = await session.execute(
            select(ExperimentMetric.id).where(
                ExperimentMetric.experiment_id == experiment_id,
                ExperimentMetric.metric_id == metric_id,
            )
        )
        return res.scalar_one_or_none() is not None

    # ----------------
    # Triggers history
    # ----------------

    @staticmethod
    async def create_trigger(
        session: AsyncSession,
        *,
        guardrail_id: UUID,
        experiment_id: UUID,
        metric_id: UUID,
        comparison_operator,
        threshold: float,
        window_minutes: int,
        action,
        actual_value: float,
        triggered_at: datetime,
    ) -> GuardrailTrigger:
        t = GuardrailTrigger(
            guardrail_id=guardrail_id,
            experiment_id=experiment_id,
            metric_id=metric_id,
            comparison_operator=comparison_operator,
            threshold=float(threshold),
            window_minutes=float(window_minutes),
            action=action,
            actual_value=float(actual_value),
            triggered_at=triggered_at,
        )
        session.add(t)
        await session.flush()
        await session.refresh(t)
        return t

    @staticmethod
    async def list_triggers_by_experiment(
        session: AsyncSession,
        *,
        experiment_id: UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[GuardrailTrigger]:
        q = (
            select(GuardrailTrigger)
            .where(GuardrailTrigger.experiment_id == experiment_id)
            .order_by(GuardrailTrigger.triggered_at.desc())
            .offset(offset)
            .limit(limit)
        )
        res = await session.execute(q)
        return res.scalars().all()

    @staticmethod
    async def count_triggers_by_experiment(
        session: AsyncSession,
        *,
        experiment_id: UUID,
    ) -> int:
        q = select(func.count(GuardrailTrigger.id)).where(
            GuardrailTrigger.experiment_id == experiment_id)
        res = await session.execute(q)
        return int(res.scalar_one())
