from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import text

from db.session import AsyncSessionLocal


READY_TIMEOUT_SECONDS = 180
READY_PROBE_INTERVAL_SECONDS = 1


@dataclass
class ReadinessState:
    startup_at: datetime
    ready: bool = False
    last_error: str | None = None
    last_checked_at: datetime | None = None

    def deadline(self) -> datetime:
        return self.startup_at + timedelta(seconds=READY_TIMEOUT_SECONDS)

    def timed_out(self) -> bool:
        return datetime.utcnow() > self.deadline()


readiness = ReadinessState(startup_at=datetime.utcnow())


async def _check_db() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT 1"))


async def probe_readiness_once() -> None:
    try:
        await _check_db()
        readiness.ready = True
        readiness.last_error = None
    except Exception as e:
        readiness.ready = False
        readiness.last_error = str(e)
    finally:
        readiness.last_checked_at = datetime.utcnow()


async def readiness_probe_loop(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        await probe_readiness_once()

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=READY_PROBE_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass
