import sqlalchemy as sa

from app.database import ensure_orchestration_columns


def test_ensure_orchestration_columns_adds_and_is_idempotent(tmp_path):
    eng = sa.create_engine(f"sqlite:///{tmp_path / 't.db'}")
    with eng.begin() as c:
        c.execute(sa.text("CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT)"))
    with eng.begin() as c:
        ensure_orchestration_columns(c, "sqlite")
        ensure_orchestration_columns(c, "sqlite")   # idempotente, nao pode quebrar
    with eng.begin() as c:
        cols = {r[1] for r in c.execute(sa.text("PRAGMA table_info(projects)"))}
    assert {"phase", "plan", "accounting_profile"} <= cols
