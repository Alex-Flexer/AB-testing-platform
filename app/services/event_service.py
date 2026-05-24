from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.event import Event, EventType
from db.repositories.decision_repo import DecisionRepository
from db.repositories.events_repo import EventRepository

from exceptions.app_exceptions import (
    AppException,
    UnprocessableEntity,
    EventTypeNotFound
)

from schemas.event import (
    EventsIn,
    EventsIngestResult,
    EventRejectInfo,
    EventTypeCreate,
)


class EventService:
    def __init__(self) -> None:
        self.repo = EventRepository
        self.decisions = DecisionRepository

    @staticmethod
    def _to_utc_naive(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt
        return dt.astimezone(timezone.utc).replace(tzinfo=None)

    async def create_event_type(self, session: AsyncSession, data: EventTypeCreate) -> EventType:
        existing = await self.repo.get_event_type_by_key(session, data.key)
        if existing is not None:
            raise UnprocessableEntity("event type with this key already exists")

        try:
            et = await self.repo.create_event_type(
                session,
                key=data.key,
                description=str(data.description),
                requires_exposure=bool(data.requires_exposure),
            )
            await session.commit()
            return et
        except IntegrityError:
            await session.rollback()
            raise UnprocessableEntity("event type with this key already exists")
        except Exception:
            await session.rollback()
            raise AppException()

    async def get_event_type(self, session: AsyncSession, key: str) -> EventType:
        et = await self.repo.get_event_type_by_key(session, key)
        if et is None:
            raise UnprocessableEntity("event type not found")
        return et

    async def list_event_types(
        self,
        session: AsyncSession,
        *,
        offset: int = 0,
        limit: int = 50,
        include_inactive: bool = False,
    ):
        if offset < 0:
            raise UnprocessableEntity("offset must be >= 0")
        if limit <= 0 or limit > 200:
            raise UnprocessableEntity("limit must be in range 1..200")

        items = await self.repo.list_event_types(
            session,
            offset=offset,
            limit=limit,
            include_inactive=include_inactive,
        )
        total = await self.repo.count_event_types(session, include_inactive=include_inactive)
        return items, total

    async def update_event_type(
        self,
        session: AsyncSession,
        key: str,
        *,
        description: Optional[str] = None,
        requires_exposure: Optional[bool] = None,
        is_active: Optional[bool] = None,
    ) -> EventType:
        et = await self.repo.get_event_type_by_key(session, key)

        if et is None:
            raise EventTypeNotFound()

        try:
            et = await self.repo.update_event_type(
                session,
                et,
                description=description,
                requires_exposure=requires_exposure,
                is_active=is_active,
            )
            await session.commit()
            return et

        except Exception:
            await session.rollback()
            raise AppException()

    async def archive_event_type(self, session: AsyncSession, key: str) -> EventType:
        return await self.update_event_type(session, key, is_active=False)

    async def ingest_events(self, session: AsyncSession, data: EventsIn) -> EventsIngestResult:
        incoming_keys = [e.idempotency_key for e in data.events]
        existing_keys = await self.repo.find_existing_idempotency_keys(session, incoming_keys)

        accepted = 0
        duplicates = 0
        rejected = 0
        errors: list[EventRejectInfo] = []

        seen_in_batch: set[str] = set()

        event_type_cache: dict[str, EventType] = {}

        decision_cache: dict[UUID, object] = {}

        events_to_insert: list[Event] = []

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        for idx, item in enumerate(data.events):
            if item.idempotency_key in seen_in_batch:
                duplicates += 1
                continue

            seen_in_batch.add(item.idempotency_key)

            if item.idempotency_key in existing_keys:
                duplicates += 1
                continue

            ts = self._to_utc_naive(item.ts)
            if ts > (now + timedelta(minutes=5)):
                rejected += 1
                errors.append(
                    EventRejectInfo(
                        index=idx,
                        idempotency_key=item.idempotency_key,
                        error="ts is too far in the future",
                    )
                )
                continue

            et = event_type_cache.get(item.event_name)
            if et is None:
                et = await self.repo.get_event_type_by_key(session, item.event_name)
                if et is None or not et.is_active:
                    rejected += 1
                    errors.append(
                        EventRejectInfo(
                            index=idx,
                            idempotency_key=item.idempotency_key,
                            error="unknown or inactive event type",
                        )
                    )
                    continue
                event_type_cache[item.event_name] = et

            decision = decision_cache.get(item.decision_id)
            if decision is None:
                decision = await self.decisions.get_by_id(session, item.decision_id)
                if decision is None:
                    rejected += 1
                    errors.append(
                        EventRejectInfo(
                            index=idx,
                            idempotency_key=item.idempotency_key,
                            error="decision not found",
                        )
                    )
                    continue
                decision_cache[item.decision_id] = decision

            ev = Event(
                decision_id=item.decision_id,
                experiment_id=decision.experiment_id,
                variant_id=decision.variant_id,
                subject_id=decision.subject_id,
                event_name=item.event_name,
                idempotency_key=item.idempotency_key,
                occurred_at=item.ts.replace(tzinfo=None),
                created_at=datetime.utcnow(),
                props=dict(item.props) if item.props is not None else {},
            )

            events_to_insert.append(ev)
            accepted += 1

        if not events_to_insert:
            return EventsIngestResult(
                accepted=accepted,
                duplicates=duplicates,
                rejected=rejected,
                errors=errors,
            )

        try:
            await self.repo.create_events(session, events_to_insert)
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise AppException("integrity error while ingesting events")

        except Exception:
            await session.rollback()
            raise AppException()

        return EventsIngestResult(
            accepted=accepted,
            duplicates=duplicates,
            rejected=rejected,
            errors=errors,
        )

    async def list_events(
        self,
        session: AsyncSession,
        *,
        experiment_id: Optional[UUID] = None,
        decision_id: Optional[UUID] = None,
        event_name: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ):
        if offset < 0:
            raise UnprocessableEntity("offset must be >= 0")
        if limit <= 0 or limit > 200:
            raise UnprocessableEntity("limit must be in range 1..200")

        items = await self.repo.list_events(
            session,
            experiment_id=experiment_id,
            decision_id=decision_id,
            event_name=event_name,
            offset=offset,
            limit=limit,
        )
        total = await self.repo.count_events(
            session,
            experiment_id=experiment_id,
            decision_id=decision_id,
            event_name=event_name,
        )
        return items, total
