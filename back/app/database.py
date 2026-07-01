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
# SQLite: o tipo JSON genérico do SQLAlchemy mapeia para TEXT (com processor de
# serialização), então TEXT é o tipo correto lá. Postgres: as colunas JSON precisam
# ser JSONB (o psycopg devolve JSONB já desserializado como dict; uma coluna TEXT
# vazaria a string crua '{}' para o schema, que espera dict).
_ORCH_COLUMNS_SQLITE = {
    "phase": "VARCHAR(20) NOT NULL DEFAULT ''",
    "plan": "TEXT NOT NULL DEFAULT '{}'",
    "accounting_profile": "TEXT NOT NULL DEFAULT '{}'",
}
_ORCH_COLUMNS_PG = {
    "phase": "VARCHAR(20) NOT NULL DEFAULT ''",
    "plan": "JSONB NOT NULL DEFAULT '{}'::jsonb",
    "accounting_profile": "JSONB NOT NULL DEFAULT '{}'::jsonb",
}
_JSON_COLS = ("plan", "accounting_profile")


def ensure_orchestration_columns(conn, dialect: str) -> None:
    """Adiciona phase/plan/accounting_profile a projects se faltarem, e no Postgres
    corrige colunas JSON que uma versão anterior criou como TEXT (auto-heal para
    JSONB). Recebe uma connection já aberta. Idempotente."""
    if dialect == "sqlite":
        existing = {row[1] for row in conn.execute(text("PRAGMA table_info(projects)"))}
        for name, ddl in _ORCH_COLUMNS_SQLITE.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE projects ADD COLUMN {name} {ddl}"))
        return
    # Postgres e compatíveis
    for name, ddl in _ORCH_COLUMNS_PG.items():
        conn.execute(text(f"ALTER TABLE projects ADD COLUMN IF NOT EXISTS {name} {ddl}"))
    # auto-heal: colunas JSON criadas como TEXT por uma versão anterior viram JSONB.
    # Guardado por data_type, então roda uma vez só; depois é no-op.
    for col in _JSON_COLS:
        dt = conn.execute(
            text(
                "select data_type from information_schema.columns "
                "where table_name = 'projects' and column_name = :c"
            ),
            {"c": col},
        ).scalar()
        if dt and dt.lower() == "text":
            conn.execute(text(f"ALTER TABLE projects ALTER COLUMN {col} TYPE jsonb USING {col}::jsonb"))
            conn.execute(text(f"ALTER TABLE projects ALTER COLUMN {col} SET DEFAULT '{{}}'::jsonb"))
