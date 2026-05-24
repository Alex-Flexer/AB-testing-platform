from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from schemas.decision import DecideRequest, DecideResponse
from services.decision_service import DecisionService

router = APIRouter(prefix="/decide", tags=["decision"])

service = DecisionService()


@router.post("", response_model=DecideResponse)
async def decide(
    data: DecideRequest,
    session: AsyncSession = Depends(get_db),
):
    return await service.decide(session, data)
