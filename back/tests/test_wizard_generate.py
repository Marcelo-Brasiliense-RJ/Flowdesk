import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Organization, Project
from app.routers import wizard


def _projeto(s):
    org = Organization(name="IRKO")
    s.add(org)
    s.flush()
    p = Project(org_id=org.id, name="x", subdomain="x")
    s.add(p)
    s.flush()
    return p


def _ws_extrato():
    return {
        "process": {"description": "extrato bancario Bradesco em PDF para lancamentos do Dominio"},
        "input": {"kind": "file", "files": [
            {"role": "extrato", "label": "Extrato"},
            {"role": "plano de contas", "label": "Plano de contas"},
            {"role": "modelo", "label": "Modelo"},
        ]},
        "output": {"kind": "download"},
    }


def test_generate_script_injeta_referencia_e_semeia(monkeypatch):
    captured = {}

    def fake_build(messages):
        captured["msgs"] = messages
        return ("ok", [{"kind": "create_file", "title": "x", "path": "p.py",
                        "content": "print('errado')"}], "")

    monkeypatch.setattr(wizard, "_generate_build", fake_build)

    eng = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        p = _projeto(s)
        explanation, code = wizard._generate_script(s, p.id, _ws_extrato())

    blob = " ".join(m["content"] for m in captured["msgs"])
    assert "IMPLEMENTAÇÃO DE REFERÊNCIA PROVADA" in blob   # few-shot injetado
    assert "def parse_extrato" in blob                     # referencia extrato-dominio
    assert "get_file(0)" in blob                           # instrucao posicional
    assert "3 arquivo" in blob                             # plano de arquivos no intent
    assert "def parse_extrato" in code                     # semeado (score alto)
    assert "print('errado')" not in code


def test_files_intent_lista_arquivos_por_indice():
    txt = wizard._files_intent({"files": [
        {"role": "extrato", "label": "Extrato", "hint": "PDF"},
        {"role": "plano", "label": "Plano de contas"},
    ]})
    assert "(0) Extrato" in txt and "(1) Plano de contas" in txt
    assert "get_file(0)" in txt and "POSICIONAL" in txt


def test_files_intent_vazio_quando_sem_plano():
    assert wizard._files_intent({}) == ""
