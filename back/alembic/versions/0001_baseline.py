"""baseline: schema atual a partir dos modelos do app

Baseline idempotente: cria as tabelas dos modelos que ainda não existem
(create_all é checkfirst). Seguro em banco NOVO (cria tudo) e em banco JÁ
EXISTENTE (não recria nada, não perde dados). Migrações futuras são autogeradas
como diffs contra Base.metadata.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-07-10
"""
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.database import Base
    import app.models  # noqa: F401  (registra as tabelas)
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    # baseline: sem downgrade (não derruba o schema inteiro)
    pass
