from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from db.enums import ExperimentStatus, UserRole
from db.models.experiment import ExperimentMetric
from db.models.user import User

from db.repositories.experiments_repo import ExperimentRepository
from db.repositories.experiments_metric_repo import ExperimentMetricRepository
from db.repositories.metrics_repo import MetricRepository

from exceptions.app_exceptions import (
    AppException,
    ExperimentNotFound,
    ExperimentStateConflict,
    UnprocessableEntity,
)
from exceptions import Forbidden


class ExperimentMetricService:
    def __init__(self) -> None:
        self.experiments = ExperimentRepository
        self.repo = ExperimentMetricRepository
        self.metrics = MetricRepository

    @staticmethod
    def _ensure_can_edit_catalog(status: ExperimentStatus):
        if status != ExperimentStatus.DRAFT:
            raise ExperimentStateConflict("experiment metrics can be edited only in DRAFT")

    @staticmethod
    def _ensure_access(exp, actor: User):
        if actor.role != UserRole.ADMIN and exp.owner_id != actor.id:
            raise Forbidden("you are allowed to edit only your experiments")

    async def attach_metric(
        self,
        session: AsyncSession,
        *,
        experiment_id: UUID,
        metric_id: UUID,
        role: str,
        actor: User,
    ):
        exp = await self.experiments.get_by_id(session, experiment_id)
        if exp is None:
            raise ExperimentNotFound()

        self._ensure_access(exp, actor)
        self._ensure_can_edit_catalog(exp.status)

        metric = await self.metrics.get_by_id(session, metric_id)
        if metric is None:
            raise UnprocessableEntity("metric not found")

        try:
            existing = await self.repo.get_link(session, experiment_id=experiment_id, metric_id=metric_id)
            if existing is not None:
                return await self.repo.update_role(session, existing, role=role)

            link = ExperimentMetric(
                experiment_id=experiment_id,
                metric_id=metric_id,
                role=role,
                created_at=datetime.utcnow(),
            )
            return await self.repo.create_link(session, link)

        except Exception:
            raise AppException()

    async def detach_metric(
        self,
        session: AsyncSession,
        *,
        experiment_id: UUID,
        metric_id: UUID,
        actor: User,
    ) -> bool:
        exp = await self.experiments.get_by_id(session, experiment_id)
        if exp is None:
            raise ExperimentNotFound()

        self._ensure_access(exp, actor)
        self._ensure_can_edit_catalog(exp.status)

        try:
            ok = await self.repo.delete_link(session, experiment_id=experiment_id, metric_id=metric_id)
            if not ok:
                raise UnprocessableEntity("metric is not attached to experiment")

            await session.commit()
            return True

        except AppException:
            await session.rollback()
            raise
        except Exception:
            await session.rollback()
            raise AppException()

    async def list_metrics(
        self,
        session: AsyncSession,
        *,
        experiment_id: UUID,
        offset: int = 0,
        limit: int = 200,
        actor: User,
    ):
        exp = await self.experiments.get_by_id(session, experiment_id)
        if exp is None:
            raise ExperimentNotFound()

        self._ensure_access(exp, actor)

        if offset < 0:
            raise UnprocessableEntity("offset must be >= 0")
        if limit <= 0 or limit > 200:
            raise UnprocessableEntity("limit must be in range 1..200")

        items = await self.repo.list_links(session, experiment_id=experiment_id, offset=offset, limit=limit)
        total = await self.repo.count_links(session, experiment_id=experiment_id)
        return items, total
