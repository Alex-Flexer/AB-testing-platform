from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_roles
from db.enums import UserRole
from db.session import get_db

from schemas.experiment_metric import (
    ExperimentMetricAttach,
    ExperimentMetricOut,
    ExperimentMetrics,
)

from services.experiment_metric_service import ExperimentMetricService


router = APIRouter(prefix="/experiments", tags=["experiment_metrics"])
service = ExperimentMetricService()


@router.post(
    "/{experiment_id}/metrics",
    response_model=ExperimentMetricOut,
)
async def attach_metric(
    experiment_id: UUID,
    data: ExperimentMetricAttach,
    session: AsyncSession = Depends(get_db),
    user=Depends(require_roles(UserRole.ADMIN, UserRole.EXPERIMENTER)),
):
    link = await service.attach_metric(
        session,
        experiment_id=experiment_id,
        metric_id=data.metric_id,
        role=str(data.role),
        actor=user,
    )
    await session.commit()
    return link


@router.get(
    "/{experiment_id}/metrics",
    response_model=ExperimentMetrics,
)
async def list_metrics(
    experiment_id: UUID,
    session: AsyncSession = Depends(get_db),
    user=Depends(require_roles(UserRole.ADMIN, UserRole.EXPERIMENTER)),
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=200),
):
    items, total = await service.list_metrics(
        session,
        experiment_id=experiment_id,
        offset=offset,
        limit=limit,
        actor=user,
    )
    return ExperimentMetrics(items=list(items), total=total)


@router.delete(
    "/{experiment_id}/metrics/{metric_id}",
)
async def detach_metric(
    experiment_id: UUID,
    metric_id: UUID,
    session: AsyncSession = Depends(get_db),
    user=Depends(require_roles(UserRole.ADMIN, UserRole.EXPERIMENTER)),
):
    await service.detach_metric(
        session,
        experiment_id=experiment_id,
        metric_id=metric_id,
        actor=user,
    )
    return {"ok": True}
