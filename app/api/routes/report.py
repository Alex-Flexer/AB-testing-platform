# api/routes/report.py

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user
from db.session import get_db
from schemas.report import ReportRequest, ExperimentReport
from services.report_service import ReportService


router = APIRouter(prefix="/reports", tags=["reports"])
service = ReportService()


@router.post(
    "/experiments/{experiment_id}",
    response_model=ExperimentReport,
)
async def experiment_report(
    experiment_id: UUID,
    data: ReportRequest,
    session: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await service.generate_experiment_report(session, experiment_id, data)
