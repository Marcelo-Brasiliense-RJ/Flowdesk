"""FlowDesk backend entrypoint.

Rode com:  python -m uvicorn main:app --host 127.0.0.1 --port 8000
(ou .\\run-dev.ps1, que ainda derruba servidores antigos antes de subir)

NAO use --reload: o runtime grava scripts .py em storage/ a cada execucao e o
watcher do --reload reiniciaria o servidor no meio da execucao, matando o teste/
publicacao (e a acao nao reflete na tela). Editou o backend? Reinicie o processo
(ou rode run-dev.ps1 de novo, que faz isso de forma limpa).
"""
from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager

# No Windows, garanta o ProactorEventLoop (necessário para subprocessos do runtime).
# Sem isso, com `--reload` o uvicorn usa um SelectorEventLoop e os scripts falham
# com NotImplementedError ao iniciar o subprocesso.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import Base, engine
from app.runtime.runner import runtime
from app.runtime.scheduler import scheduler
from app import metrics
from app.routers import (
    admin,
    ai,
    auth,
    builds,
    chat,
    classify,
    dashboard,
    executions,
    filemanager,
    hooks,
    manage,
    projects,
    published,
    realtime,
    repair,
    settings as settings_router,
    templates,
    wizard,
)
from app.seed import seed_if_empty


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    # índices para colunas consultadas com frequência (seguro em DB existente)
    with engine.begin() as conn:
        for stmt in (
            "CREATE INDEX IF NOT EXISTS ix_exec_project_started ON executions (project_id, started_at)",
            "CREATE INDEX IF NOT EXISTS ix_exec_stage ON executions (stage_id)",
            "CREATE INDEX IF NOT EXISTS ix_stage_project ON stages (project_id)",
            "CREATE INDEX IF NOT EXISTS ix_edge_project ON edges (project_id)",
            "CREATE INDEX IF NOT EXISTS ix_srcfile_project ON source_files (project_id)",
            "CREATE INDEX IF NOT EXISTS ix_chat_project ON chat_messages (project_id)",
        ):
            conn.execute(text(stmt))
        # micro-migração SQLite: colunas novas em DB já existente
        # (PRAGMA é específico do SQLite; no Postgres/Supabase o schema já vem
        # com essas colunas, então não rodamos isto lá).
        if engine.dialect.name == "sqlite":
            proj_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(projects)"))}
            if "wizard_state" not in proj_cols:
                conn.execute(
                    text("ALTER TABLE projects ADD COLUMN wizard_state TEXT NOT NULL DEFAULT '{}'")
                )
            if "wizard_dirty" not in proj_cols:
                conn.execute(
                    text("ALTER TABLE projects ADD COLUMN wizard_dirty BOOLEAN NOT NULL DEFAULT 0")
                )
            if "created_by_id" not in proj_cols:
                conn.execute(
                    text("ALTER TABLE projects ADD COLUMN created_by_id INTEGER")
                )
            user_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(users)"))}
            if "role" not in user_cols:
                conn.execute(
                    text("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'")
                )
        else:
            # Postgres aceita IF NOT EXISTS
            conn.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'user'")
            )
            conn.execute(
                text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS created_by_id INTEGER")
            )
        # ceifador de zumbis: execuções queued/running de processos anteriores
        # nunca vão terminar; marca como erro para não poluir métricas e monitor.
        conn.execute(
            text(
                "UPDATE executions SET status='error', "
                "stderr = stderr || '\n[runtime] Execução encerrada: o servidor foi reiniciado.' "
                "WHERE status IN ('queued','running')"
            )
        )
    seed_if_empty()
    from app.seed import heal_seed_scripts
    heal_seed_scripts()
    loop = asyncio.get_event_loop()
    runtime.start(loop)
    scheduler.start(loop)
    yield


app = FastAPI(title="FlowDesk API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def _count_requests(request, call_next):
    metrics.record_request(request.method)
    return await call_next(request)


for module in (
    auth,
    admin,
    ai,
    classify,
    projects,
    executions,
    builds,
    filemanager,
    settings_router,
    chat,
    published,
    realtime,
    dashboard,
    hooks,
    wizard,
    repair,
    manage,
    templates,
):
    app.include_router(module.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "ai_enabled": settings.ai_enabled}
