from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_roles
from db.enums import UserRole
from db.session import get_db

from schemas.guardrail import GuardrailCreate, Guardrails, GuardrailOut, GuardrailTriggers, GuardrailUpdate
from services.guardrail_service import GuardrailService

router = APIRouter(prefix="/experiments/{experiment_id}/guardrails", tags=["guardrails"])
service = GuardrailService()


@router.post("", response_model=GuardrailOut)
async def create_guardrail(
    experiment_id: UUID,
    data: GuardrailCreate,
    session: AsyncSession = Depends(get_db),
    user=Depends(require_roles(UserRole.ADMIN, UserRole.EXPERIMENTER)),
):
    return await service.create_guardrail(session, experiment_id, data)


@router.get("", response_model=Guardrails)
async def list_guardrails(
    experiment_id: UUID,
    session: AsyncSession = Depends(get_db),
    user=Depends(require_roles(UserRole.ADMIN, UserRole.EXPERIMENTER,
                 UserRole.APPROVER, UserRole.VIEWER)),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    enabled_only: bool = False,
):
    items, total = await service.list_guardrails(
        session,
        experiment_id,
        offset=offset,
        limit=limit,
        enabled_only=enabled_only,
    )
    return Guardrails(items=list(items), total=total)


@router.delete("/{guardrail_id}")
async def delete_guardrail(
    experiment_id: UUID,
    guardrail_id: UUID,
    session: AsyncSession = Depends(get_db),
    user=Depends(require_roles(UserRole.ADMIN, UserRole.EXPERIMENTER)),
):
    ok = await service.delete_guardrail(session, experiment_id, guardrail_id)
    return {"ok": bool(ok)}


@router.post("/evaluate")
async def evaluate_guardrails(
    experiment_id: UUID,
    session: AsyncSession = Depends(get_db),
    user=Depends(require_roles(UserRole.ADMIN)),
):
    results = await service.evaluate_guardrails(session, experiment_id)
    return {
        "experiment_id": str(experiment_id),
        "results": [
            {
                "guardrail_id": str(r.guardrail_id),
                "triggered": r.triggered,
                "actual_value": r.actual_value,
                "threshold": r.threshold,
                "action": r.action,
            }
            for r in results
        ],
    }


@router.get("/triggers", response_model=GuardrailTriggers)
async def list_guardrail_triggers(
    experiment_id: UUID,
    session: AsyncSession = Depends(get_db),
    user=Depends(require_roles(UserRole.ADMIN, UserRole.EXPERIMENTER,
                 UserRole.APPROVER, UserRole.VIEWER)),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    items, total = await service.list_triggers(session, experiment_id, offset=offset, limit=limit)
    return GuardrailTriggers(items=list(items), total=total)


@router.patch(
    "/{guardrail_id}",
    response_model=GuardrailOut,
)
async def update_guardrail(
    experiment_id: UUID,
    guardrail_id: UUID,
    data: GuardrailUpdate,
    session: AsyncSession = Depends(get_db),
    user=Depends(require_roles(UserRole.ADMIN, UserRole.EXPERIMENTER)),
):
    return await service.update_guardrail(
        session,
        experiment_id=experiment_id,
        guardrail_id=guardrail_id,
        data=data,
        actor=user,
    )
