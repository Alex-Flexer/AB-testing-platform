from __future__ import annotations

from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.event import Event, EventType


class EventRepository:
    # ----------------
    # EventType catalog
    # ----------------

    @staticmethod
    async def get_event_type_by_key(session: AsyncSession, key: str) -> Optional[EventType]:
        res = await session.execute(select(EventType).where(EventType.key == key))
        return res.scalar_one_or_none()

    @staticmethod
    async def get_event_type_by_id(session: AsyncSession, event_type_id: UUID) -> Optional[EventType]:
        res = await session.execute(select(EventType).where(EventType.id == event_type_id))
        return res.scalar_one_or_none()

    @staticmethod
    async def list_event_types(
        session: AsyncSession,
        *,
        offset: int = 0,
        limit: int = 50,
        include_inactive: bool = False,
    ) -> Sequence[EventType]:
        q = select(EventType).order_by(EventType.created_at.desc()).offset(offset).limit(limit)
        if not include_inactive:
            q = q.where(EventType.is_active.is_(True))
        res = await session.execute(q)
        return res.scalars().all()

    @staticmethod
    async def count_event_types(session: AsyncSession, *, include_inactive: bool = False) -> int:
        q = select(func.count(EventType.id))
        if not include_inactive:
            q = q.select_from(EventType).where(EventType.is_active.is_(True))
        res = await session.execute(q)
        return int(res.scalar_one())

    @staticmethod
    async def create_event_type(
        session: AsyncSession,
        *,
        key: str,
        description: str,
        requires_exposure: bool,
    ) -> EventType:
        et = EventType(
            key=key,
            description=description,
            requires_exposure=requires_exposure,
            is_active=True,
        )
        session.add(et)
        await session.flush()
        await session.refresh(et)
        return et

    @staticmethod
    async def update_event_type(
        session: AsyncSession,
        et: EventType,
        description: Optional[str] = None,
        requires_exposure: Optional[bool] = None,
        is_active: Optional[bool] = None,
    ) -> EventType:
        if description is not None:
            et.description = description

        if requires_exposure is not None:
            et.requires_exposure = bool(requires_exposure)

        if is_active is not None:
            et.is_active = bool(is_active)

        session.add(et)
        await session.flush()
        await session.refresh(et)
        return et

    # -------------
    # Events ingest
    # -------------

    @staticmethod
    async def find_existing_idempotency_keys(
        session: AsyncSession,
        keys: list[str],
    ) -> set[str]:
        if not keys:
            return set()

        res = await session.execute(select(Event.idempotency_key).where(Event.idempotency_key.in_(keys)))
        return set(res.scalars().all())

    @staticmethod
    async def create_events(session: AsyncSession, events: list[Event]) -> None:
        for e in events:
            session.add(e)
        await session.flush()

    @staticmethod
    async def exposure_exists_for_decision(
        session: AsyncSession,
        *,
        decision_id: UUID,
        exposure_event_name: str = "exposure",
    ) -> bool:
        res = await session.execute(
            select(func.count(Event.id)).where(
                Event.decision_id == decision_id,
                Event.event_name == exposure_event_name,
            )
        )
        return int(res.scalar_one()) > 0

    # -----------------
    # Optional: browsing
    # -----------------

    @staticmethod
    async def list_events(
        session: AsyncSession,
        *,
        experiment_id: Optional[UUID] = None,
        decision_id: Optional[UUID] = None,
        event_name: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[Event]:
        q = select(Event).order_by(Event.created_at.desc()).offset(offset).limit(limit)

        if experiment_id is not None:
            q = q.where(Event.experiment_id == experiment_id)

        if decision_id is not None:
            q = q.where(Event.decision_id == decision_id)

        if event_name is not None:
            q = q.where(Event.event_name == event_name)

        res = await session.execute(q)
        return res.scalars().all()

    @staticmethod
    async def count_events(
        session: AsyncSession,
        *,
        experiment_id: Optional[UUID] = None,
        decision_id: Optional[UUID] = None,
        event_name: Optional[str] = None,
    ) -> int:
        q = select(func.count(Event.id))

        if experiment_id is not None:
            q = q.where(Event.experiment_id == experiment_id)

        if decision_id is not None:
            q = q.where(Event.decision_id == decision_id)

        if event_name is not None:
            q = q.where(Event.event_name == event_name)

        res = await session.execute(q)
        return int(res.scalar_one())
