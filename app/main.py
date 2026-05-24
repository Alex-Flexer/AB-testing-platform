import uvicorn
import asyncio
from datetime import datetime, UTC

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.routes.feature_flags import router as flags_router
from api.routes.users import router as users_router
from api.routes.auth import router as auth_router
from api.routes.experiments import router as experiment_router
from api.routes.decision import router as decision_router
from api.routes.events import router as events_router
from api.routes.metrics import router as metrics_router
from api.routes.report import router as report_router
from api.routes.guardrails import router as guardrails_router
from api.routes.experiment_metrics import router as experiment_metrics_router
from api.routes.health import router as health_router

from core.health import readiness, readiness_probe_loop

from exceptions.app_exceptions import AppException

from db.init_db import init_db


app = FastAPI()

app.include_router(flags_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(experiment_router)
app.include_router(decision_router)
app.include_router(events_router)
app.include_router(metrics_router)
app.include_router(report_router)
app.include_router(guardrails_router)
app.include_router(experiment_metrics_router)
app.include_router(health_router)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.on_event("startup")
async def on_startup():
    readiness.startup_at = datetime.now(UTC)
    readiness.ready = False
    readiness.last_error = None
    readiness.last_checked_at = None

    await init_db()

    app.state._ready_stop = asyncio.Event()
    app.state._ready_task = asyncio.create_task(readiness_probe_loop(app.state._ready_stop))


if __name__ == "__main__":
    uvicorn.run(app, port=80, host="0.0.0.0")
