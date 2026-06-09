"""Lightweight scheduler for Job stages (interval / daily).

Runs in-process alongside the runtime. Every CHECK_INTERVAL seconds it scans
enabled Job stages and enqueues an execution when due, using the stage's last
execution time as the gate (so it survives restarts).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import uuid
from typing import Optional

from ..database import SessionLocal
from ..models import Execution, Stage
from .runner import runtime

CHECK_INTERVAL = 30

_UNIT_SECONDS = {"minutes": 60, "hours": 3600, "days": 86400}


def _interval_seconds(sched: dict) -> int:
    every = max(1, int(sched.get("every", 1)))
    return every * _UNIT_SECONDS.get(sched.get("unit", "hours"), 3600)


class Scheduler:
    def __init__(self) -> None:
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.task: Optional[asyncio.Task] = None

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.task = loop.create_task(self._run())

    async def _run(self) -> None:
        while True:
            try:
                self._tick()
            except Exception:
                pass
            await asyncio.sleep(CHECK_INTERVAL)

    def _tick(self) -> None:
        db = SessionLocal()
        try:
            now = dt.datetime.utcnow()
            jobs = db.query(Stage).filter(Stage.type == "job").all()
            for job in jobs:
                cfg = job.config or {}
                if not cfg.get("enabled"):
                    continue
                sched = cfg.get("schedule") or {}
                stype = sched.get("type")
                if stype not in ("interval", "daily"):
                    continue

                last = (
                    db.query(Execution)
                    .filter(Execution.stage_id == job.id)
                    .order_by(Execution.started_at.desc())
                    .first()
                )
                last_at = last.started_at if last else None
                if last_at is not None and last_at.tzinfo is not None:
                    last_at = last_at.replace(tzinfo=None)

                due = False
                if stype == "interval":
                    secs = _interval_seconds(sched)
                    due = last_at is None or (now - last_at).total_seconds() >= secs
                elif stype == "daily":
                    try:
                        hh, mm = map(int, str(sched.get("time", "08:00")).split(":"))
                    except Exception:
                        hh, mm = 8, 0
                    sched_today = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                    due = now >= sched_today and (last_at is None or last_at < sched_today)

                if due:
                    execu = Execution(
                        id=str(uuid.uuid4()),
                        project_id=job.project_id,
                        stage_id=job.id,
                        stage_name=job.name,
                        stage_type="job",
                        status="queued",
                        input_data={"trigger": "schedule"},
                    )
                    db.add(execu)
                    db.commit()
                    runtime.submit(execu.id)
        finally:
            db.close()


scheduler = Scheduler()
