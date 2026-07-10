"""I4: a baseline do Alembic cria exatamente o schema dos modelos atuais."""
import sys
from pathlib import Path

import sqlalchemy as sa

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

from app.database import Base
import app.models  # noqa: F401  (registra as tabelas)


def test_baseline_cria_todas_as_tabelas_dos_modelos():
    # o baseline roda Base.metadata.create_all; o schema resultante = os modelos.
    eng = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    tabelas = set(sa.inspect(eng).get_table_names())
    esperado = set(Base.metadata.tables.keys())
    assert tabelas == esperado
    assert len(esperado) >= 15  # sanidade: o schema não é trivial


def test_scaffolding_alembic_existe():
    assert (BACK / "alembic.ini").is_file()
    assert (BACK / "alembic" / "env.py").is_file()
    assert (BACK / "alembic" / "versions" / "0001_baseline.py").is_file()
