from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from schemas.feature_flag import (
    FeatureFlagCreate,
    FeatureFlagUpdate,
    FeatureFlagOut,
    FeatureFlags,
)
from services.feature_flag_service import FeatureFlagService
from api.deps import require_admin


router = APIRouter(prefix="/flags", tags=["feature_flags"])
service = FeatureFlagService()


@router.post("/", response_model=FeatureFlagOut, dependencies=[Depends(require_admin)])
async def create_flag(data: FeatureFlagCreate, session: AsyncSession = Depends(get_db)):
    return await service.create_flag(session, data)


@router.get("/{flag_id}", response_model=FeatureFlagOut, dependencies=[Depends(require_admin)])
async def get_flag(flag_id: UUID, session: AsyncSession = Depends(get_db)):
    return await service.get_flag(session, flag_id)


@router.get("/", response_model=FeatureFlags, dependencies=[Depends(require_admin)])
async def list_flags(
    session: AsyncSession = Depends(get_db),
    offset: int = 0,
    limit: int = 50,
):
    items, total = await service.list_flags(session, offset=offset, limit=limit)
    return FeatureFlags(items=list(items), total=total)


@router.patch("/{flag_id}", response_model=FeatureFlagOut, dependencies=[Depends(require_admin)])
async def update_flag(flag_id: UUID, data: FeatureFlagUpdate, session: AsyncSession = Depends(get_db)):
    return await service.update_flag(session, flag_id, data)


@router.delete("/{flag_id}", dependencies=[Depends(require_admin)])
async def delete_flag(flag_id: UUID, session: AsyncSession = Depends(get_db)):
    await service.delete_flag(session, flag_id)
    return {"ok": True}
