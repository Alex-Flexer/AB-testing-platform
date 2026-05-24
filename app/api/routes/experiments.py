from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, require_roles
from db.enums import UserRole
from db.session import get_db
from schemas.experiment import (
    ExperimentCreate,
    ExperimentUpdate,
    ExperimentOut,
    Experiments,
    ExperimentSubmitForReview,
    ExperimentReviewDecision,
)
from services.experiment_service import ExperimentService


router = APIRouter(prefix="/experiments", tags=["experiments"])

service = ExperimentService()


@router.post(
    "/",
    response_model=ExperimentOut,
)
async def create_experiment(
    data: ExperimentCreate,
    session: AsyncSession = Depends(get_db),
    user=Depends(require_roles(UserRole.ADMIN, UserRole.EXPERIMENTER)),
):
    # user — это текущий пользователь (уже проверен JWT и роль)
    # owner_id проставляем из токена, а не берём из body
    experiment_id = await service.create_experiment(session, owner_id=user.id, data=data)
    return await service.get_experiment(session, experiment_id=experiment_id)


@router.get(
    "/{experiment_id}",
    response_model=ExperimentOut,
)
async def get_experiment(
    experiment_id: UUID,
    session: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    # доступ: любой авторизованный (или можно ограничить)
    return await service.get_experiment(session, experiment_id=experiment_id)


@router.get(
    "/",
    response_model=Experiments,
)
async def list_experiments(
    session: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    owner_id: UUID | None = None,
    feature_flag_id: UUID | None = None,
    status: str | None = None,
):
    items, total = await service.list_experiments(
        session,
        offset=offset,
        limit=limit,
        status=status,
    )
    return Experiments(items=items, total=total)


@router.patch(
    "/{experiment_id}",
    response_model=ExperimentOut,
)
async def update_experiment(
    experiment_id: UUID,
    data: ExperimentUpdate,
    session: AsyncSession = Depends(get_db),
    user=Depends(require_roles(UserRole.ADMIN, UserRole.EXPERIMENTER)),
):
    # В сервисе: проверка, что можно менять только DRAFT,
    # и что экспериментер может менять только свои эксперименты, а админ — любые.
    return await service.update_experiment(
        session,
        experiment_id=experiment_id,
        data=data,
        actor=user,
    )


@router.delete(
    "/{experiment_id}",
)
async def delete_experiment(
    experiment_id: UUID,
    session: AsyncSession = Depends(get_db),
    user=Depends(require_roles(UserRole.ADMIN, UserRole.EXPERIMENTER)),
):
    # Реши: hard delete или "soft" (например статус = stopped/archived)
    await service.delete_experiment(session, experiment_id=experiment_id, actor=user)
    return {"ok": True}


# -------------------------
# Lifecycle: review / start / pause / stop
# -------------------------

@router.post(
    "/{experiment_id}/submit",
    response_model=ExperimentOut,
)
async def submit_for_review(
    experiment_id: UUID,
    data: ExperimentSubmitForReview,
    session: AsyncSession = Depends(get_db),
    user=Depends(require_roles(UserRole.ADMIN, UserRole.EXPERIMENTER)),
):
    # В сервисе: только владелец/админ, только из DRAFT -> IN_REVIEW
    return await service.submit_for_review(
        session,
        experiment_id=experiment_id,
        actor=user,
    )


@router.post(
    "/{experiment_id}/review",
    response_model=ExperimentOut,
)
async def review_experiment(
    experiment_id: UUID,
    data: ExperimentReviewDecision,
    session: AsyncSession = Depends(get_db),
    user=Depends(require_roles(UserRole.ADMIN, UserRole.APPROVER)),
):
    return await service.review_experiment(
        session,
        experiment_id=experiment_id,
        actor=user,
        decision=data.decision,
        comment=data.comment,
    )


@router.post(
    "/{experiment_id}/start",
    response_model=ExperimentOut,
)
async def start_experiment(
    experiment_id: UUID,
    session: AsyncSession = Depends(get_db),
    user=Depends(require_roles(UserRole.ADMIN, UserRole.EXPERIMENTER)),
):
    return await service.start_experiment(session, experiment_id=experiment_id, actor=user)


@router.post(
    "/{experiment_id}/pause",
    response_model=ExperimentOut,
)
async def pause_experiment(
    experiment_id: UUID,
    session: AsyncSession = Depends(get_db),
    user=Depends(require_roles(UserRole.ADMIN, UserRole.EXPERIMENTER)),
):
    return await service.pause_experiment(session, experiment_id=experiment_id, actor=user)


@router.post(
    "/{experiment_id}/resume",
    response_model=ExperimentOut,
)
async def resume_experiment(
    experiment_id: UUID,
    session: AsyncSession = Depends(get_db),
    user=Depends(require_roles(UserRole.ADMIN, UserRole.EXPERIMENTER)),
):
    return await service.resume_experiment(session, experiment_id=experiment_id, actor=user)


@router.post(
    "/{experiment_id}/stop",
    response_model=ExperimentOut,
)
async def stop_experiment(
    experiment_id: UUID,
    session: AsyncSession = Depends(get_db),
    user=Depends(require_roles(UserRole.ADMIN, UserRole.EXPERIMENTER)),
):
    return await service.stop_experiment(session, experiment_id=experiment_id, actor=user)


@router.post(
    "/{experiment_id}/archive",
    response_model=ExperimentOut,
)
async def archive_experiment(
    experiment_id: UUID,
    session: AsyncSession = Depends(get_db),
    user=Depends(require_roles(UserRole.ADMIN, UserRole.EXPERIMENTER)),
):
    return await service.archive_experiment(session, experiment_id=experiment_id, actor=user)
