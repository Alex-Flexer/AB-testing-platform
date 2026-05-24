from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, require_roles
from db.enums import UserRole
from db.session import get_db

from schemas.metric import MetricCreate, MetricUpdate, MetricOut, Metrics
from services.metric_service import MetricService


router = APIRouter(prefix="/metrics", tags=["metrics"])
service = MetricService()


@router.post(
    "/",
    response_model=MetricOut,
)
async def create_metric(
    data: MetricCreate,
    session: AsyncSession = Depends(get_db),
    user=Depends(require_roles(UserRole.ADMIN, UserRole.EXPERIMENTER)),
):
    return await service.create_metric(session, data, created_by=user.id)


@router.get(
    "/{metric_id}",
    response_model=MetricOut,
)
async def get_metric(
    metric_id: UUID,
    session: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await service.get_metric(session, metric_id)


@router.get(
    "/",
    response_model=Metrics,
)
async def list_metrics(
    session: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    items, total = await service.list_metrics(session, offset=offset, limit=limit)
    return Metrics(items=list(items), total=total)


@router.patch(
    "/{metric_id}",
    response_model=MetricOut,
)
async def update_metric(
    metric_id: UUID,
    data: MetricUpdate,
    session: AsyncSession = Depends(get_db),
    user=Depends(require_roles(UserRole.ADMIN, UserRole.EXPERIMENTER)),
):
    return await service.update_metric(session, metric_id, data)


@router.delete(
    "/{metric_id}",
    dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.EXPERIMENTER))],
)
async def delete_metric(
    metric_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    await service.delete_metric(session, metric_id)
    return {"ok": True}
