from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_admin
from db.session import get_db
from schemas.event import (
    EventsIn,
    EventsIngestResult,
    EventTypeCreate,
    EventTypeOut
)
from services.event_service import EventService

router = APIRouter(prefix="/events", tags=["events"])
service = EventService()


# -------------------------
# Ingest (product -> platform)
# -------------------------

@router.post("", response_model=EventsIngestResult)
async def ingest_events(
    data: EventsIn,
    session: AsyncSession = Depends(get_db),
):
    return await service.ingest_events(session, data)


# -------------------------
# Event Types Catalog (admin)
# -------------------------

@router.post(
    "/types",
    response_model=EventTypeOut,
    dependencies=[Depends(require_admin)],
)
async def create_event_type(
    data: EventTypeCreate,
    session: AsyncSession = Depends(get_db),
):
    return await service.create_event_type(session, data)


@router.get(
    "/types",
    dependencies=[Depends(require_admin)],
)
async def list_event_types(
    session: AsyncSession = Depends(get_db),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    include_inactive: bool = False,
):
    items, total = await service.list_event_types(
        session,
        offset=offset,
        limit=limit,
        include_inactive=include_inactive,
    )
    return {"items": items, "total": total}


@router.get(
    "/types/{key}",
    response_model=EventTypeOut,
    dependencies=[Depends(require_admin)],
)
async def get_event_type(
    key: str,
    session: AsyncSession = Depends(get_db),
):
    return await service.get_event_type(session, key)


@router.patch(
    "/types/{key}",
    response_model=EventTypeOut,
    dependencies=[Depends(require_admin)],
)
async def update_event_type(
    key: str,
    description: str | None = None,
    requires_exposure: bool | None = None,
    is_active: bool | None = None,
    session: AsyncSession = Depends(get_db),
):
    return await service.update_event_type(
        session,
        key,
        description=description,
        requires_exposure=requires_exposure,
        is_active=is_active,
    )


@router.post(
    "/types/{key}/archive",
    response_model=EventTypeOut,
    dependencies=[Depends(require_admin)],
)
async def archive_event_type(
    key: str,
    session: AsyncSession = Depends(get_db),
):
    return await service.archive_event_type(session, key)


# -------------------------
# Optional: inspect events (admin)
# -------------------------

@router.get(
    "",
    dependencies=[Depends(require_admin)],
)
async def list_events(
    session: AsyncSession = Depends(get_db),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    experiment_id: UUID | None = None,
    decision_id: UUID | None = None,
    event_name: str | None = None,
):
    items, total = await service.list_events(
        session,
        offset=offset,
        limit=limit,
        experiment_id=experiment_id,
        decision_id=decision_id,
        event_name=event_name,
    )
    return {"items": items, "total": total}
