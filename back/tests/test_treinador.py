from app.services import treinador


def test_store_reads_empty_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(treinador, "_DIR", tmp_path / "treinador")
    assert treinador._examples() == []
    assert treinador._proposals() == []
    assert treinador._repairs() == []


def test_treinador_has_default_prompt():
    assert isinstance(treinador.TREINADOR_PROMPT, str)
    assert treinador.TREINADOR_PROMPT.strip()


import datetime as dt
from app.models import Base, Organization, Project, Execution
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _mem_db():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    return Session(eng)


def _proj(db, status="live"):
    org = Organization(name="IRKO")
    db.add(org); db.flush()
    p = Project(org_id=org.id, name="P", subdomain="p", status=status)
    db.add(p); db.flush()
    return p


def _exec(db, pid, status, minutes_ago):
    e = Execution(
        id=f"{pid}-{status}-{minutes_ago}", project_id=pid, stage_id=1,
        status=status,
        started_at=dt.datetime(2026, 1, 1) + dt.timedelta(minutes=100 - minutes_ago),
    )
    db.add(e); db.flush()
    return e


def test_validated_needs_live_success_and_no_recent_error():
    db = _mem_db()
    p = _proj(db, status="live")
    _exec(db, p.id, "success", 1)
    assert treinador.is_validated(db, p.id) is True


def test_not_validated_when_recent_error():
    db = _mem_db()
    p = _proj(db, status="live")
    _exec(db, p.id, "success", 5)
    _exec(db, p.id, "error", 1)  # erro recente derruba
    assert treinador.is_validated(db, p.id) is False


def test_not_validated_when_draft():
    db = _mem_db()
    p = _proj(db, status="draft")
    _exec(db, p.id, "success", 1)
    assert treinador.is_validated(db, p.id) is False


def test_not_validated_without_any_success():
    db = _mem_db()
    p = _proj(db, status="live")
    assert treinador.is_validated(db, p.id) is False
