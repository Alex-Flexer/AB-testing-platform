from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.decision import Decision


class DecisionRepository:
    @staticmethod
    async def get_by_id(session: AsyncSession, decision_id: UUID) -> Decision | None:
        res = await session.execute(select(Decision).where(Decision.id == decision_id))
        return res.scalar_one_or_none()

    @staticmethod
    async def get_by_experiment_subject(
        session: AsyncSession,
        experiment_id: UUID,
        subject_id: str,
    ) -> Decision | None:
        res = await session.execute(
            select(Decision).where(
                Decision.experiment_id == experiment_id,
                Decision.subject_id == subject_id,
            )
        )
        return res.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        decision: Decision,
    ) -> Decision:
        session.add(decision)
        await session.flush()
        return decision

    @staticmethod
    async def delete_by_id(session: AsyncSession, decision_id: UUID) -> bool:
        res = await session.execute(delete(Decision).where(Decision.id == decision_id))
        return (res.rowcount or 0) > 0
