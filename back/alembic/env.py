"""Ambiente do Alembic. Usa o engine e o metadata do próprio app (SQLite local ou
Postgres/Supabase conforme a config), então as migrações batem com os modelos reais."""
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context

# back/ no path para importar o app
BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

from app.database import Base, engine  # noqa: E402
import app.models  # noqa: E402,F401  (registra todas as tabelas em Base.metadata)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite: ALTER via batch
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
