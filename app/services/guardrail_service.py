from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.enums import (
    GuardrailAction,
    ComparisonOperator,
    ExperimentStatus,
    AggregationType,
    UserRole
)
from db.models.event import Event
from db.models.experiment import Experiment

from db.repositories.guardrails_repo import GuardrailRepository
from db.repositories.experiments_repo import ExperimentRepository

from exceptions.app_exceptions import (
    AppException,
    UnprocessableEntity,
    ExperimentNotFound,
    ExperimentStateConflict,
    MetricNotFound,
    Forbidden,
)
from schemas.guardrail import GuardrailCreate, GuardrailUpdate


@dataclass
class GuardrailEvalResult:
    guardrail_id: UUID
    triggered: bool
    actual_value: float
    threshold: float
    action: str


class GuardrailService:
    def __init__(self):
        self.repo = GuardrailRepository
        self.experiments = ExperimentRepository

    async def create_guardrail(self, session: AsyncSession, experiment_id: UUID, data: GuardrailCreate):
        exp = await self.experiments.get_by_id(session, experiment_id)
        if exp is None:
            raise ExperimentNotFound()

        metric = await self.repo.get_metric_by_key(session, data.metric_key)
        if metric is None:
            raise MetricNotFound()

        linked = await self.repo.is_metric_linked_to_experiment(
            session,
            experiment_id=experiment_id,
            metric_id=metric.id,
        )
        if not linked:
            raise UnprocessableEntity("metric is not linked to experiment")

        try:
            g = await self.repo.create(
                session,
                experiment_id=experiment_id,
                metric_id=metric.id,
                comparison_operator=data.comparison_operator,
                threshold=float(data.threshold),
                window_minutes=int(data.window_minutes),
                action=data.action,
                enabled=bool(data.enabled),
            )
            await session.commit()
            return await self.repo.get_by_id(session, g.id)

        except Exception:
            await session.rollback()
            raise AppException()

    async def list_guardrails(
        self,
        session: AsyncSession,
        experiment_id: UUID,
        *,
        offset: int = 0,
        limit: int = 50,
        enabled_only: bool = False,
    ):
        if offset < 0:
            raise UnprocessableEntity("offset must be >= 0")

        if limit <= 0 or limit > 200:
            raise UnprocessableEntity("limit must be in range 1..200")

        exp = await self.experiments.get_by_id(session, experiment_id)
        if exp is None:
            raise ExperimentNotFound()

        items = await self.repo.list_by_experiment(
            session,
            experiment_id=experiment_id,
            offset=offset,
            limit=limit,
            enabled_only=enabled_only,
        )
        total = await self.repo.count_by_experiment(session, experiment_id=experiment_id, enabled_only=enabled_only)
        return items, total

    async def delete_guardrail(self, session: AsyncSession, experiment_id: UUID, guardrail_id: UUID):
        exp = await self.experiments.get_by_id(session, experiment_id)
        if exp is None:
            raise ExperimentNotFound()

        g = await self.repo.get_by_id(session, guardrail_id)
        if g is None or g.experiment_id != experiment_id:
            raise UnprocessableEntity("guardrail not found")

        try:
            ok = await self.repo.delete_by_id(session, guardrail_id)
            await session.commit()
            return ok
        except Exception:
            await session.rollback()
            raise AppException()

    async def update_guardrail(
        self,
        session: AsyncSession,
        *,
        experiment_id: UUID,
        guardrail_id: UUID,
        data: GuardrailUpdate,
        actor,
    ):
        exp = await self.experiments.get_by_id(session, experiment_id)
        if exp is None:
            raise ExperimentNotFound()

        if actor.role != UserRole.ADMIN and exp.owner_id != actor.id:
            raise Forbidden("you are allowed to edit only your experiments")

        guardrail = await self.repo.get_by_id(session, guardrail_id)
        if guardrail is None or guardrail.experiment_id != experiment_id:
            raise UnprocessableEntity("guardrail not found for this experiment")

        if getattr(data, "metric_key", None) is not None:
            metric = await self.metrics.get_by_key(session, str(data.metric_key))
            if metric is None:
                raise UnprocessableEntity("metric not found")

            linked = await self.exp_metrics.exists(session, experiment_id=experiment_id, metric_id=metric.id)
            if not linked:
                raise UnprocessableEntity(
                    "metric must be attached to experiment before using as guardrail")

            guardrail.metric_id = metric.id

        if data.comparison_operator is not None:
            guardrail.comparison_operator = data.comparison_operator

        if data.threshold is not None:
            guardrail.threshold = float(data.threshold)

        if data.window_minutes is not None:
            guardrail.window_minutes = int(data.window_minutes)

        if data.action is not None:
            guardrail.action = data.action

        if data.enabled is not None:
            guardrail.enabled = bool(data.enabled)

        try:
            session.add(guardrail)
            await session.commit()

            return await self.repo.get_by_id(session, guardrail.id)

        except Exception:
            await session.rollback()
            raise AppException()

    @staticmethod
    def _cmp(op: ComparisonOperator, actual: float, threshold: float) -> bool:
        if op == ComparisonOperator.GT:
            return actual > threshold
        if op == ComparisonOperator.GTE:
            return actual >= threshold
        if op == ComparisonOperator.LT:
            return actual < threshold
        if op == ComparisonOperator.LTE:
            return actual <= threshold
        raise AppException("unsupported comparison_operator")

    @staticmethod
    def _get_prop_value(props: dict, path: str):
        cur = props
        for part in path.split("."):
            if isinstance(cur, dict):
                if part not in cur:
                    return None

                cur = cur[part]

            elif isinstance(cur, list):
                if not part.isdigit() or len(part) >= len(cur):
                    return None

                cur = cur[int(part)]

            else:
                return None

        return cur

    async def _fetch_events_window(self, session: AsyncSession, *, experiment_id: UUID, from_ts: datetime):
        res = await session.execute(
            select(Event).where(
                Event.experiment_id == experiment_id,
                Event.occurred_at >= from_ts,
            )
        )
        return list(res.scalars().all())

    async def _calc_metric_value(
        self,
        session: AsyncSession,
        *,
        experiment_id: UUID,
        metric,
        window_minutes: int,
    ) -> float:
        now = datetime.utcnow()
        from_ts = now - timedelta(minutes=int(window_minutes))

        events = await self._fetch_events_window(session, experiment_id=experiment_id, from_ts=from_ts)

        agg = metric.aggregation_type

        if agg in (AggregationType.COUNT, AggregationType.UNIQUE_COUNT):
            if not metric.numerator_event:
                return 0.0

            matched = [e for e in events if e.event_name == metric.numerator_event]

            if agg == AggregationType.COUNT:
                return float(len(matched))

            return float(len({e.subject_id for e in matched}))

        if agg == AggregationType.RATE:
            if not metric.numerator_event or not metric.denominator_event:
                return 0.0

            num = sum(1 for e in events if e.event_name == metric.numerator_event)
            den = sum(1 for e in events if e.event_name == metric.denominator_event)

            if den == 0:
                return 0.0

            return float(num) / float(den)

        if agg in (AggregationType.AVG, AggregationType.P95):
            if not metric.field_path:
                return 0.0

            if metric.numerator_event:
                src = [e for e in events if e.event_name == metric.numerator_event]
            else:
                src = events

            values: list[float] = []
            for e in src:
                props = e.props or {}
                v = self._get_prop_value(props, metric.field_path)
                if isinstance(v, bool):
                    continue
                if isinstance(v, (int, float)):
                    values.append(float(v))
                elif isinstance(v, str):
                    try:
                        values.append(float(v))
                    except Exception:
                        pass

            if not values:
                return 0.0

            if agg == AggregationType.AVG:
                return float(sum(values)) / float(len(values))

            values.sort()
            idx = int((0.95 * (len(values) - 1)))
            return float(values[idx])

        return 0.0

    async def _apply_action(self, session: AsyncSession, exp: Experiment, action: GuardrailAction):
        if exp.status != ExperimentStatus.RUNNING:
            return

        if action == GuardrailAction.PAUSE:
            exp.status = ExperimentStatus.PAUSED
            return

        if action == GuardrailAction.ROLLBACK_TO_CONTROL:
            exp.status = ExperimentStatus.PAUSED
            exp.traffic_percentage = 0.0
            return

        raise AppException("unknown guardrail action")

    async def evaluate_guardrails(self, session: AsyncSession, experiment_id: UUID) -> list[GuardrailEvalResult]:
        exp = await self.experiments.get_by_id(session, experiment_id)
        if exp is None:
            raise ExperimentNotFound()

        if exp.status != ExperimentStatus.RUNNING:
            raise ExperimentStateConflict(
                "guardrails can be evaluated only when experiment is RUNNING")

        guardrails = await self.repo.list_by_experiment(
            session,
            experiment_id=experiment_id,
            enabled_only=True,
            offset=0,
            limit=200,
        )

        results: list[GuardrailEvalResult] = []
        now = datetime.utcnow()

        for g in guardrails:
            metric = await session.get(type(g.metric), g.metric_id) if hasattr(g, "metric") else None
            if metric is None:
                from db.models.metric import Metric
                metric = await session.get(Metric, g.metric_id)

            actual = await self._calc_metric_value(
                session,
                experiment_id=experiment_id,
                metric=metric,
                window_minutes=int(g.window_minutes),
            )

            triggered = self._cmp(g.comparison_operator, actual, float(g.threshold))

            if triggered:
                exp_db = await session.get(Experiment, experiment_id)
                await self._apply_action(session, exp_db, g.action)

                await self.repo.create_trigger(
                    session,
                    guardrail_id=g.id,
                    experiment_id=experiment_id,
                    metric_id=g.metric_id,
                    comparison_operator=g.comparison_operator,
                    threshold=float(g.threshold),
                    window_minutes=int(g.window_minutes),
                    action=g.action,
                    actual_value=float(actual),
                    triggered_at=now,
                )

            results.append(
                GuardrailEvalResult(
                    guardrail_id=g.id,
                    triggered=bool(triggered),
                    actual_value=float(actual),
                    threshold=float(g.threshold),
                    action=g.action.value,
                )
            )

        try:
            await session.commit()
        except Exception:
            await session.rollback()
            raise AppException()

        return results

    async def list_triggers(self, session: AsyncSession, experiment_id: UUID, *, offset: int = 0, limit: int = 50):
        if offset < 0:
            raise UnprocessableEntity("offset must be >= 0")
        if limit <= 0 or limit > 200:
            raise UnprocessableEntity("limit must be in range 1..200")

        exp = await self.experiments.get_by_id(session, experiment_id)
        if exp is None:
            raise ExperimentNotFound()

        items = await self.repo.list_triggers_by_experiment(session, experiment_id=experiment_id, offset=offset, limit=limit)
        total = await self.repo.count_triggers_by_experiment(session, experiment_id=experiment_id)
        return items, total
