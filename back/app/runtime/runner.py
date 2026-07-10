"""Script execution runtime: FIFO asyncio queue + subprocess worker.

Each Script stage runs in an isolated Python subprocess with the project's
environment variables injected. stdout/stderr are captured and persisted per
execution; status changes are broadcast over WebSocket to the workflow monitor.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import re
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


def _is_transient_import_error(stderr: str) -> bool:
    """Falhas intermitentes de import de numpy/pandas em cold start no Windows
    (a primeira carga dos .pyd às vezes é interrompida ou falha no PyCapsule).
    Uma nova tentativa costuma resolver, então vale re-executar uma vez."""
    s = stderr or ""
    return (
        "PyCapsule_Import could not import module" in s
        or ("KeyboardInterrupt" in s and "import" in s.lower())
        or ("numpy" in s and "_multiarray" in s)
    )


# S1: allowlist de variáveis de ambiente do SO repassadas ao subprocesso (nomes
# comparados em UPPERCASE, pois o Windows é case-insensitive). São vars não
# secretas necessárias para o interpretador iniciar e as libs nativas (numpy/
# pandas, DLLs) carregarem. Segredos do servidor (SECRET_KEY, OPENAI_API_KEY,
# SUPABASE_DB_URL, SMTP_*) ficam de fora por não estarem nesta lista.
# ponytail: allowlist > denylist. Um segredo novo no ambiente não vaza sozinho.
_ENV_PASSTHROUGH = {
    name.upper()
    for name in (
        # Windows
        "SystemRoot", "windir", "SystemDrive", "PATHEXT", "COMSPEC",
        "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "PROCESSOR_ARCHITEW6432",
        "LOCALAPPDATA", "APPDATA", "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)",
        "COMMONPROGRAMFILES", "TEMP", "TMP",
        # POSIX / cross-platform (deploy Linux futuro, ver I2 do dossiê)
        "PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE",
        "TZ", "TMPDIR", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH",
    )
}


def _last_error_line(stderr: str) -> str:
    """Ultima linha significativa de um traceback, para virar mensagem legivel ao
    usuario (o campo 'erro' que o app publicado ja exibe). Prefere a linha da
    excecao (ex.: 'ValueError: ...'), cai na ultima linha nao vazia."""
    linhas = [ln.strip() for ln in (stderr or "").splitlines() if ln.strip()]
    if not linhas:
        return "A automacao falhou sem mensagem. Verifique os arquivos de entrada."
    for ln in reversed(linhas):
        if re.match(r"^[\w.]+(Error|Exception|Warning|Erro)\b", ln):
            return ln[:300]
    return linhas[-1][:300]


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
                if not (execu.output_data or {}).get("erro"):
                    execu.output_data = {**(execu.output_data or {}),
                                         "erro": _last_error_line(execu.stderr)}
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
            execu.run_dir = str(run_dir)
            # tabelas internas do projeto disponíveis ao script (ex: regras De/Para)
            from ..models import DataRow, DataTable

            tables: dict[str, list] = {}
            for t in db.query(DataTable).filter(DataTable.project_id == project.id):
                rows = db.query(DataRow).filter(DataRow.table_id == t.id).all()
                tables[t.name] = [r.values for r in rows]
            (run_dir / "tables.json").write_text(
                json.dumps(tables, ensure_ascii=False), encoding="utf-8"
            )

            env_vars = {
                ev.key: ev.value
                for ev in db.query(EnvVar).filter(EnvVar.project_id == project.id)
            }
            entry = stage.entry_file or f"{stage.key}.py"

            spawn_kwargs = dict(
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
            code, out, err = await self._spawn(**spawn_kwargs)
            # cold start de numpy/pandas falha de forma intermitente no Windows;
            # uma única nova tentativa resolve sem mascarar erros reais de código.
            if code != 0 and not output_path.exists() and _is_transient_import_error(err):
                code, out, err = await self._spawn(**spawn_kwargs)

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
            execu.status = "success" if code == 0 else "error"
            # falha dura sem saida gravada: sintetiza uma mensagem legivel no mesmo
            # canal 'erro' que o app publicado e o ReportCard ja exibem.
            if (execu.status == "error" and not output_data.get("erro")
                    and not output_data.get("arquivo_resultado")):
                output_data = {**output_data, "erro": _last_error_line(err)}
            execu.output_data = output_data
            execu.finished_at = _utcnow()
            db.commit()

            # job agendado que falhou: avisa por e-mail (best-effort, opcional)
            if execu.status == "error" and stage.type == "job":
                from ..services.notify import notify_job_failure

                notify_job_failure(project.name, stage.name, execu.id, err)

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

        from ..config import settings

        # S1: sandbox opt-in. Default "subprocess" mantém o caminho on-premise.
        if settings.execution_backend == "container":
            from .container import run_in_container

            return await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: run_in_container(
                    src_dir=src_dir,
                    output_dir=output_dir,
                    run_dir=run_dir,
                    entry=entry,
                    env_vars=env_vars,
                    timeout=timeout,
                ),
            )

        # S1: NUNCA herdar os.environ inteiro. O script é gerado por IA e editável;
        # o ambiente do servidor tem SECRET_KEY (assina JWT de admin), OPENAI_API_KEY,
        # SUPABASE_DB_URL, SMTP_PASSWORD. Só passamos o mínimo de SO para o Python e as
        # libs nativas (numpy/pandas) iniciarem, mais as EnvVar do projeto.
        env = {k: v for k, v in os.environ.items() if k.upper() in _ENV_PASSTHROUGH}
        env.update({k: str(v) for k, v in env_vars.items()})
        env["FLOWDESK_INPUT"] = str(input_path)
        env["FLOWDESK_OUTPUT"] = str(output_path)
        env["FLOWDESK_OUTPUT_DIR"] = str(output_dir)
        env["FLOWDESK_RUN_DIR"] = str(run_dir)
        # PYTHONPATH isolado: só o src_dir do projeto, sem herdar o do servidor
        # (herdar exporia os módulos do app ao script).
        env["PYTHONPATH"] = str(src_dir)
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
