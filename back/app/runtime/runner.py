"""Script execution runtime: FIFO asyncio queue + subprocess worker.

Each Script stage runs in an isolated Python subprocess with the project's
environment variables injected. stdout/stderr are captured and persisted per
execution; status changes are broadcast over WebSocket to the workflow monitor.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import uuid
from pathlib import Path
from typing import Optional

from ..config import settings
from ..database import SessionLocal
from ..models import Edge, EnvVar, Execution, Project, Stage
from ..services import storage
from ..services.ws import hub


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class RuntimeManager:
    def __init__(self) -> None:
        self.queue: "asyncio.Queue[str]" = asyncio.Queue()
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._worker: Optional[asyncio.Task] = None
        # rolling stats for the monitor
        self._durations: list[float] = []

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self._worker = loop.create_task(self._run_worker())

    def submit(self, execution_id: str) -> None:
        """Thread-safe enqueue (callable from sync request handlers)."""
        if self.loop is None:
            raise RuntimeError("Runtime not started")
        self.loop.call_soon_threadsafe(self.queue.put_nowait, execution_id)

    def pending_count(self) -> int:
        return self.queue.qsize()

    def avg_duration(self) -> float:
        if not self._durations:
            return 0.0
        return sum(self._durations) / len(self._durations)

    async def _broadcast(self, project_id: int, payload: dict) -> None:
        await hub.broadcast(project_id, payload)

    async def _run_worker(self) -> None:
        while True:
            execution_id = await self.queue.get()
            try:
                await self._execute(execution_id)
            except Exception as exc:  # never let the worker die
                self._fail_silently(execution_id, str(exc))
            finally:
                self.queue.task_done()

    def _fail_silently(self, execution_id: str, message: str) -> None:
        db = SessionLocal()
        try:
            execu = db.get(Execution, execution_id)
            if execu:
                execu.status = "error"
                execu.stderr = (execu.stderr or "") + f"\n[runtime] {message}"
                execu.finished_at = _utcnow()
                db.commit()
        finally:
            db.close()

    async def _execute(self, execution_id: str) -> None:
        db = SessionLocal()
        try:
            execu = db.get(Execution, execution_id)
            if execu is None:
                return
            stage = db.get(Stage, execu.stage_id)
            project = db.get(Project, execu.project_id)
            if stage is None or project is None:
                return

            execu.status = "running"
            execu.started_at = _utcnow()
            db.commit()
            await self._broadcast(
                project.id,
                {"type": "execution", "execution_id": execu.id,
                 "stage_id": stage.id, "status": "running"},
            )

            root = storage.ensure_project_dirs(project)
            src_dir = storage.materialize_sources(db, project)
            run_dir = root / "runs" / execu.id
            run_dir.mkdir(parents=True, exist_ok=True)
            input_path = run_dir / "input.json"
            output_path = run_dir / "output.json"
            input_path.write_text(
                json.dumps(execu.input_data or {}, ensure_ascii=False),
                encoding="utf-8",
            )

            env_vars = {
                ev.key: ev.value
                for ev in db.query(EnvVar).filter(EnvVar.project_id == project.id)
            }
            entry = stage.entry_file or f"{stage.key}.py"

            code, out, err = await self._spawn(
                src_dir=src_dir,
                cwd=root,
                entry=entry,
                input_path=input_path,
                output_path=output_path,
                output_dir=root / project.output_folder_name,
                run_dir=run_dir,
                env_vars=env_vars,
                timeout=stage.timeout_seconds or 120,
            )

            output_data: dict = {}
            if output_path.exists():
                try:
                    parsed = json.loads(output_path.read_text(encoding="utf-8"))
                    # scripts may write a non-dict; always store a dict
                    output_data = parsed if isinstance(parsed, dict) else {"resultado": parsed}
                except json.JSONDecodeError:
                    output_data = {}

            execu.stdout = out
            execu.stderr = err
            execu.output_data = output_data
            execu.status = "success" if code == 0 else "error"
            execu.finished_at = _utcnow()
            db.commit()

            duration = (execu.finished_at - execu.started_at).total_seconds()
            self._durations = (self._durations + [duration])[-50:]

            await self._broadcast(
                project.id,
                {"type": "execution", "execution_id": execu.id,
                 "stage_id": stage.id, "status": execu.status},
            )

            if execu.status == "success":
                await self._chain_next(db, project, stage, output_data, execu.build_id)
        finally:
            db.close()

    async def _spawn(
        self,
        *,
        src_dir: Path,
        cwd: Path,
        entry: str,
        input_path: Path,
        output_path: Path,
        output_dir: Path,
        run_dir: Path,
        env_vars: dict,
        timeout: int,
    ) -> tuple[int, str, str]:
        import os

        env = os.environ.copy()
        env.update({k: str(v) for k, v in env_vars.items()})
        env["FLOWDESK_INPUT"] = str(input_path)
        env["FLOWDESK_OUTPUT"] = str(output_path)
        env["FLOWDESK_OUTPUT_DIR"] = str(output_dir)
        env["FLOWDESK_RUN_DIR"] = str(run_dir)
        env["PYTHONPATH"] = str(src_dir) + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTHONIOENCODING"] = "utf-8"

        script_path = src_dir / entry

        def _cap(b: bytes, limit: int = 100_000) -> str:
            s = b.decode("utf-8", "replace")
            return s if len(s) <= limit else s[:limit] + "\n[...saída truncada...]"

        # subprocess SÍNCRONO numa thread: funciona em qualquer event loop
        # (o asyncio subprocess exige ProactorEventLoop no Windows, que o uvicorn
        # com --reload nem sempre usa).
        import subprocess

        def _blocking():
            try:
                r = subprocess.run(
                    [settings.python_executable, str(script_path)],
                    cwd=str(cwd),
                    env=env,
                    capture_output=True,
                    timeout=timeout,
                )
                return r.returncode, _cap(r.stdout), _cap(r.stderr)
            except subprocess.TimeoutExpired as e:
                err = _cap(e.stderr or b"") + f"\n[runtime] Tempo limite de {timeout}s excedido."
                return 1, _cap(e.stdout or b""), err

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _blocking)

    async def _chain_next(
        self,
        db,
        project: Project,
        stage: Stage,
        output_data: dict,
        build_id: Optional[int],
    ) -> None:
        """Auto-advance to downstream script/job stages (forms are user gates)."""
        edges = (
            db.query(Edge)
            .filter(Edge.project_id == project.id, Edge.source_stage_id == stage.id)
            .all()
        )
        for edge in edges:
            target = db.get(Stage, edge.target_stage_id)
            if target is None or target.type not in ("script", "job"):
                continue
            execu = Execution(
                id=str(uuid.uuid4()),
                project_id=project.id,
                stage_id=target.id,
                build_id=build_id,
                stage_name=target.name,
                stage_type=target.type,
                status="queued",
                input_data=output_data,
            )
            db.add(execu)
            db.commit()
            self.submit(execu.id)


runtime = RuntimeManager()
