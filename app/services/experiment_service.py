from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from db.enums import ExperimentStatus, ReviewDecision

from db.models.experiment import Experiment, ExperimentVersion
from db.models.variant import Variant
from db.models.user import User

from db.enums import UserRole

from db.repositories.experiments_repo import ExperimentRepository
from db.repositories.feature_flags_repo import FeatureFlagRepository

from exceptions.app_exceptions import (
    AppException,
    UnprocessableEntity,
    ExperimentNotFound,
    FeatureFlagNotFound,
    ExperimentStateConflict,
)

from schemas.experiment import ExperimentCreate, ExperimentUpdate

from exceptions import Forbidden


class ExperimentService:
    def __init__(self):
        self.repo = ExperimentRepository
        self.flags = FeatureFlagRepository

    @staticmethod
    def _ensure_can_edit_config(status: ExperimentStatus):
        if status != ExperimentStatus.DRAFT:
            raise ExperimentStateConflict("experiment config can be edited only in DRAFT")

    @staticmethod
    def _snapshot_config(exp: Experiment, variants: list[Variant]) -> dict:
        return {
            "name": exp.name,
            "description": exp.description,
            "traffic_percentage": exp.traffic_percentage,
            "targeting_rule": getattr(exp, "targeting_rule", None),
            "feature_flag_id": str(exp.feature_flag_id),
            "variants": [
                {
                    "id": str(v.id),
                    "name": v.name,
                    "value": v.value,
                    "weight": v.weight,
                    "is_control": v.is_control,
                }
                for v in (variants or [])
            ],
        }

    async def _create_version(
        self,
        session: AsyncSession,
        exp: Experiment,
        created_by: UUID | None,
        variants: list[Variant] | None = None
    ):
        v = ExperimentVersion(
            experiment_id=exp.id,
            version=exp.current_version,
            config=self._snapshot_config(exp, variants),
            created_by=created_by,
            created_at=datetime.utcnow()
        )
        session.add(v)
        await session.flush()
        return v

    async def create_experiment(self, session: AsyncSession, data: ExperimentCreate, *, owner_id: UUID):
        flag = await self.flags.get_by_id(session, data.feature_flag_id)
        if flag is None:
            raise FeatureFlagNotFound()

        try:
            exp = Experiment(
                name=data.name,
                description=data.description,
                status=ExperimentStatus.DRAFT,
                traffic_percentage=float(data.traffic_percentage),
                start_at=None,
                end_at=None,
                feature_flag_id=data.feature_flag_id,
                owner_id=owner_id,
                created_at=datetime.utcnow(),
                current_version=1,
            )

            await self.repo.create(session, exp)

            variants = [
                Variant(
                    experiment_id=exp.id,
                    name=v.name,
                    value=v.value,
                    weight=float(v.weight),
                    is_control=bool(v.is_control),
                )
                for v in data.variants
            ]

            await self.repo.add_variants(session, exp.id, variants)

            await self._create_version(session, exp, created_by=owner_id, variants=variants)

            await session.commit()
            return exp.id

        except IntegrityError:
            await session.rollback()
            raise UnprocessableEntity("integrity error")

        except Exception as e:
            print(e)
            await session.rollback()
            raise AppException()

    async def get_experiment(self, session: AsyncSession, experiment_id: UUID) -> Experiment:
        exp = await self.repo.get_by_id(session, experiment_id)
        if exp is None:
            raise ExperimentNotFound()
        return exp

    async def list_experiments(self, session: AsyncSession, offset: int = 0, limit: int = 50, status: str | None = None):
        if offset < 0:
            raise UnprocessableEntity("offset must be >= 0")

        if limit <= 0 or limit > 200:
            raise UnprocessableEntity("limit must be in range 1..200")

        items = await self.repo.list(session, offset=offset, limit=limit, status=status)
        total = await self.repo.count(session, status=status)
        return items, total

    async def update_experiment(self, session: AsyncSession, experiment_id: UUID, data: ExperimentUpdate, *, actor: User):
        exp = await self.repo.get_by_id(session, experiment_id)

        if exp is None:
            raise ExperimentNotFound()

        self._ensure_can_edit_config(exp.status)

        if actor.role != UserRole.ADMIN and exp.owner_id != actor.id:
            raise Forbidden("you are allowed to edit only your experiments")

        if data.name is not None:
            exp.name = data.name

        if data.description is not None:
            exp.description = data.description

        if data.traffic_percentage is not None:
            exp.traffic_percentage = float(data.traffic_percentage)

        if getattr(data, "targeting_rule", None) is not None:
            exp.targeting_rule = data.targeting_rule

        exp.current_version += 1

        try:
            await session.flush()
            exp = await self.repo.get_by_id(session, experiment_id)
            await self._create_version(session, exp, created_by=actor.id)

            await session.commit()
            return exp

        except Exception:
            await session.rollback()
            raise AppException()

    async def delete_experiment(self, session: AsyncSession, experiment_id: UUID, actor: User):
        exp = await self.repo.get_by_id(session, experiment_id)

        if exp is None:
            raise ExperimentNotFound()

        if actor.role != UserRole.ADMIN and exp.owner_id != actor.id:
            raise Forbidden("you are allowed to delete only your experiments")

        if exp.status != ExperimentStatus.DRAFT:
            raise ExperimentStateConflict("only DRAFT experiments can be deleted")

        try:
            ok = await self.repo.delete_by_id(session, experiment_id)
            await session.commit()

        except Exception:
            await session.rollback()
            raise AppException()

        if not ok:
            raise ExperimentNotFound()

        return True

    async def submit_for_review(self, session: AsyncSession, experiment_id: UUID, actor: User):
        exp = await self.repo.get_by_id(session, experiment_id)

        if actor.role != UserRole.ADMIN and exp.owner_id != actor.id:
            raise Forbidden("you are allowed to submit for review only your experiments")

        if exp is None:
            raise ExperimentNotFound()

        if exp.status != ExperimentStatus.DRAFT:
            raise ExperimentStateConflict("only DRAFT experiments can be submitted for review")

        exp.status = ExperimentStatus.IN_REVIEW

        try:
            await session.commit()
            return exp

        except Exception:
            await session.rollback()
            raise AppException()

    async def review_experiment(
        self,
        session: AsyncSession,
        experiment_id: UUID,
        decision: ReviewDecision,
        actor: User,
        comment: str
    ):
        exp = await self.repo.get_by_id(session, experiment_id)

        if exp is None:
            raise ExperimentNotFound()

        if actor.role != UserRole.ADMIN and exp.owner_id != actor.id:
            raise Forbidden("you are allowed to review only your experiments")

        if exp.status != ExperimentStatus.IN_REVIEW:
            raise ExperimentStateConflict("experiment must be IN_REVIEW")

        if decision == ReviewDecision.APPROVE:
            exp.status = ExperimentStatus.APPROVED
        else:
            exp.status = ExperimentStatus.DRAFT

        try:
            await session.commit()
            return exp

        except Exception:
            await session.rollback()
            raise AppException()

    async def start_experiment(self, session: AsyncSession, experiment_id: UUID, actor: User):
        exp = await self.repo.get_by_id(session, experiment_id)

        if exp is None:
            raise ExperimentNotFound()

        if actor.role != UserRole.ADMIN and exp.owner_id != actor.id:
            raise Forbidden("you are allowed to start only your experiments")

        if exp.status != ExperimentStatus.APPROVED:
            raise ExperimentStateConflict("only APPROVED experiments can be started")

        exp.status = ExperimentStatus.RUNNING
        exp.start_at = datetime.utcnow()

        try:
            await session.commit()
            return exp

        except Exception:
            await session.rollback()
            raise AppException()

    async def pause_experiment(self, session: AsyncSession, experiment_id: UUID, actor: User):
        exp = await self.repo.get_by_id(session, experiment_id)

        if exp is None:
            raise ExperimentNotFound()

        if actor.role != UserRole.ADMIN and exp.owner_id != actor.id:
            raise Forbidden("you are allowed to pause only your experiments")

        if exp.status != ExperimentStatus.RUNNING:
            raise ExperimentStateConflict("only RUNNING experiments can be paused")

        exp.status = ExperimentStatus.PAUSED

        try:
            await session.commit()
            return exp

        except Exception:
            await session.rollback()
            raise AppException()

    async def resume_experiment(self, session: AsyncSession, experiment_id: UUID, actor: User):
        exp = await self.repo.get_by_id(session, experiment_id)

        if exp is None:
            raise ExperimentNotFound()

        if actor.role != UserRole.ADMIN and exp.owner_id != actor.id:
            raise Forbidden("you are allowed to resume only your experiments")

        if exp.status != ExperimentStatus.PAUSED:
            raise ExperimentStateConflict("only PAUSED experiments can be resumed")

        exp.status = ExperimentStatus.RUNNING

        try:
            await session.commit()
            return exp

        except Exception:
            await session.rollback()
            raise AppException()

    async def stop_experiment(self, session: AsyncSession, experiment_id: UUID, actor: User):
        exp = await self.repo.get_by_id(session, experiment_id)

        if exp is None:
            raise ExperimentNotFound()

        if actor.role != UserRole.ADMIN and exp.owner_id != actor.id:
            raise Forbidden("you are allowed to stop only your experiments")

        if exp.status not in (ExperimentStatus.RUNNING, ExperimentStatus.PAUSED):
            raise ExperimentStateConflict("only RUNNING or PAUSED experiments can be stopped")

        exp.status = ExperimentStatus.STOPPED
        exp.end_at = datetime.utcnow()

        try:
            await session.commit()
            return exp

        except Exception:
            await session.rollback()
            raise AppException()

    async def archive_experiment(self, session: AsyncSession, experiment_id: UUID, actor: User):
        exp = await self.repo.get_by_id(session, experiment_id)

        if exp is None:
            raise ExperimentNotFound()

        if actor.role != UserRole.ADMIN and exp.owner_id != actor.id:
            raise Forbidden("you are allowed to archive only your experiments")

        if exp.status == ExperimentStatus.STOPPED:
            raise ExperimentStateConflict("only STOPPED experiments can be stopped")

        exp.status = ExperimentStatus.ARCHIVED
        exp.end_at = datetime.utcnow()

        try:
            await session.commit()
            return exp

        except Exception:
            await session.rollback()
            raise AppException()
