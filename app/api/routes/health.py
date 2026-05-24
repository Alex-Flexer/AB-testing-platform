from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core.health import readiness

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return JSONResponse(status_code=200, content={"status": "ok"})


@router.get("/ready")
async def ready():
    if readiness.ready:
        return JSONResponse(
            status_code=200,
            content={"status": "ready"}
        )

    return JSONResponse(
        status_code=503,
        content={"status": "not_ready"}
    )
