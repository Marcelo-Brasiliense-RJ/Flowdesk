"""SQLAlchemy engine, session factory and FastAPI dependency."""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import DB_PATH, settings

_db_url = settings.db_url
if _db_url:
    # Postgres (Supabase). Usa o driver psycopg v3.
    if _db_url.startswith("postgresql://"):
        _db_url = _db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(_db_url, pool_pre_ping=True)
else:
    # Fallback: SQLite local.
    engine = create_engine(
        f"sqlite:///{DB_PATH}",
        connect_args={"check_same_thread": False},
    )
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Colunas de orquestração (Fase 2) adicionadas a bancos já existentes.
# SQLite nao cria colunas novas via create_all; seguimos o mesmo padrao de
# micro-migração do lifespan (ver back/main.py). Idempotente.
_ORCH_COLUMNS = {
    "phase": "VARCHAR(20) NOT NULL DEFAULT ''",
    "plan": "TEXT NOT NULL DEFAULT '{}'",
    "accounting_profile": "TEXT NOT NULL DEFAULT '{}'",
}


def ensure_orchestration_columns(conn, dialect: str) -> None:
    """Adiciona phase/plan/accounting_profile a projects se faltarem. Recebe uma
    connection já aberta. Idempotente em SQLite (PRAGMA) e Postgres (IF NOT EXISTS)."""
    if dialect == "sqlite":
        existing = {row[1] for row in conn.execute(text("PRAGMA table_info(projects)"))}
        for name, ddl in _ORCH_COLUMNS.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE projects ADD COLUMN {name} {ddl}"))
    else:
        for name, ddl in _ORCH_COLUMNS.items():
            conn.execute(text(f"ALTER TABLE projects ADD COLUMN IF NOT EXISTS {name} {ddl}"))
