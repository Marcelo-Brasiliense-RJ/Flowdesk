import datetime as dt

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, Execution, Organization, Project, SourceFile
from app.services import treinador


def test_store_reads_empty_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(treinador, "_DIR", tmp_path / "treinador")
    assert treinador._examples() == []
    assert treinador._proposals() == []
    assert treinador._repairs() == []


def test_treinador_has_default_prompt():
    assert isinstance(treinador.TREINADOR_PROMPT, str)
    assert treinador.TREINADOR_PROMPT.strip()


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


def test_validated_ignores_error_beyond_last_5():
    db = _mem_db()
    p = _proj(db, status="live")
    # erro mais antigo (fora da janela das 5 mais recentes)
    _exec(db, p.id, "error", 60)
    # 5 sucessos mais recentes
    for minutes_ago in (5, 4, 3, 2, 1):
        _exec(db, p.id, "success", minutes_ago)
    assert treinador.is_validated(db, p.id) is True


def _file(db, pid, path, content, is_dir=False):
    f = SourceFile(project_id=pid, path=path, content=content, is_dir=is_dir)
    db.add(f); db.flush()
    return f


def test_source_fingerprint_is_order_independent():
    db1 = _mem_db()
    p1 = _proj(db1, status="live")
    _file(db1, p1.id, "a.py", "print(1)")
    _file(db1, p1.id, "b.py", "print(2)")

    db2 = _mem_db()
    p2 = _proj(db2, status="live")
    # mesmo conjunto, ordem de insercao invertida
    _file(db2, p2.id, "b.py", "print(2)")
    _file(db2, p2.id, "a.py", "print(1)")

    fp1 = treinador._source_fingerprint(db1, p1.id)
    fp2 = treinador._source_fingerprint(db2, p2.id)
    assert fp1 == fp2


def test_source_fingerprint_is_sha1_hex():
    db = _mem_db()
    p = _proj(db, status="live")
    _file(db, p.id, "a.py", "print(1)")
    fp = treinador._source_fingerprint(db, p.id)
    assert len(fp) == 40
    assert all(c in "0123456789abcdef" for c in fp)


def test_source_fingerprint_changes_with_content():
    db = _mem_db()
    p = _proj(db, status="live")
    _file(db, p.id, "a.py", "print(1)")
    fp_before = treinador._source_fingerprint(db, p.id)

    f = db.query(SourceFile).filter_by(project_id=p.id, path="a.py").one()
    f.content = "print(2)"
    db.flush()

    fp_after = treinador._source_fingerprint(db, p.id)
    assert fp_before != fp_after


def test_source_fingerprint_skips_dirs():
    db = _mem_db()
    p = _proj(db, status="live")
    _file(db, p.id, "a.py", "print(1)")
    fp_before = treinador._source_fingerprint(db, p.id)

    _file(db, p.id, "subdir", "", is_dir=True)
    fp_after = treinador._source_fingerprint(db, p.id)

    assert fp_before == fp_after


def _example(contabil, fonte_fmt, saida_fmt, regra, code="x"):
    return {
        "plan": {
            "contabil": contabil,
            "fonte": {"formato": fonte_fmt},
            "saida": {"formato": saida_fmt},
            "regra_negocio": regra,
        },
        "code": code, "fingerprint": regra, "project_id": 1,
    }


def test_select_prefers_same_format_and_contabil(monkeypatch, tmp_path):
    monkeypatch.setattr(treinador, "_DIR", tmp_path / "treinador")
    treinador._save(treinador._examples_path(), {"items": [
        _example(True, "xlsx", "xlsx", "conciliação de razão contábil", code="A"),
        _example(False, "csv", "pdf", "relatório de vendas mensal", code="B"),
        _example(True, "xlsx", "xlsx", "aging de contas a receber", code="C"),
    ]})
    plan = {"contabil": True, "fonte": {"formato": "xlsx"},
            "saida": {"formato": "xlsx"}, "regra_negocio": "conciliação de razão"}
    picked = treinador.select_examples(plan, k=2)
    assert len(picked) == 2
    codes = {e["code"] for e in picked}
    assert "B" not in codes  # nada em comum, score 0 -> fora
    assert "A" in codes      # maior overlap de regra_negocio


def test_examples_context_empty_when_no_match(monkeypatch, tmp_path):
    monkeypatch.setattr(treinador, "_DIR", tmp_path / "treinador")
    treinador._save(treinador._examples_path(), {"items": []})
    assert treinador.examples_context({"contabil": False}) == ""


def test_harvest_skips_when_not_validated(monkeypatch, tmp_path):
    monkeypatch.setattr(treinador, "_DIR", tmp_path / "treinador")
    db = _mem_db()
    p = _proj(db, status="draft")  # não validado
    monkeypatch.setattr(treinador, "SessionLocal", lambda: db)
    assert treinador.harvest_project(p.id) is False
    assert treinador._examples() == []


def test_harvest_stores_once_then_dedups(monkeypatch, tmp_path):
    monkeypatch.setattr(treinador, "_DIR", tmp_path / "treinador")
    db = _mem_db()
    p = _proj(db, status="live")
    _exec(db, p.id, "success", 1)
    db.add(SourceFile(project_id=p.id, path="processar.py", content="print(1)"))
    p.plan = {"contabil": False, "fonte": {"formato": "xlsx"},
              "saida": {"formato": "xlsx"}, "regra_negocio": "somar colunas"}
    db.flush()
    monkeypatch.setattr(treinador, "SessionLocal", lambda: db)
    # anonimização mockada (sem IA de verdade nos testes)
    monkeypatch.setattr(treinador, "anonymize_plan", lambda plan: plan)
    assert treinador.harvest_project(p.id) is True
    assert len(treinador._examples()) == 1
    # segunda chamada com o mesmo código: dedup, não grava de novo
    assert treinador.harvest_project(p.id) is False
    assert len(treinador._examples()) == 1


def test_harvest_does_not_store_when_anonymize_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(treinador, "_DIR", tmp_path / "treinador")
    db = _mem_db()
    p = _proj(db, status="live")
    _exec(db, p.id, "success", 1)
    db.add(SourceFile(project_id=p.id, path="processar.py", content="print(1)"))
    p.plan = {"contabil": False, "fonte": {"formato": "xlsx"},
              "saida": {"formato": "xlsx"}, "regra_negocio": "somar colunas"}
    db.flush()
    monkeypatch.setattr(treinador, "SessionLocal", lambda: db)
    # anonimização falhou (IA indisponível/resposta inválida) -> nada pode ser gravado
    monkeypatch.setattr(treinador, "anonymize_plan", lambda plan: None)
    assert treinador.harvest_project(p.id) is False
    assert treinador._examples() == []


def test_harvest_does_not_store_when_no_python_code(monkeypatch, tmp_path):
    monkeypatch.setattr(treinador, "_DIR", tmp_path / "treinador")
    db = _mem_db()
    p = _proj(db, status="live")
    _exec(db, p.id, "success", 1)
    # sem arquivo .py com conteúdo: só um arquivo vazio
    db.add(SourceFile(project_id=p.id, path="processar.py", content=""))
    p.plan = {"contabil": False, "fonte": {"formato": "xlsx"},
              "saida": {"formato": "xlsx"}, "regra_negocio": "somar colunas"}
    db.flush()
    monkeypatch.setattr(treinador, "SessionLocal", lambda: db)
    monkeypatch.setattr(treinador, "anonymize_plan", lambda plan: plan)
    assert treinador.harvest_project(p.id) is False
    assert treinador._examples() == []


def test_harvest_never_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(treinador, "_DIR", tmp_path / "treinador")
    def _boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(treinador, "SessionLocal", _boom)
    # best-effort: engole tudo, retorna False
    assert treinador.harvest_project(1) is False
