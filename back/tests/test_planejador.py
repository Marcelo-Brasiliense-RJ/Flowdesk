import json

from app.routers import orchestrator


def test_planejador_merges_plan_and_reports_missing(monkeypatch):
    fake = json.dumps({
        "questions": [{"id": "saida", "label": "Qual o formato de saida?",
                       "options": ["Excel", "CSV"], "recommended": "Excel"}],
        "plan": {"fonte": {"formato": "xlsx"}, "regra_negocio": "somar por cliente"},
        "contabil": False,
    })
    monkeypatch.setattr(orchestrator, "call_agent", lambda *a, **k: fake)
    out = orchestrator.run_planejador([{"role": "user", "content": "somar planilha"}], {})
    assert out["plan"]["fonte"]["formato"] == "xlsx"
    assert out["plan"]["regra_negocio"] == "somar por cliente"
    assert "saida.formato" in out["missing"] and "gatilho" in out["missing"]
    assert "fonte.formato" not in out["missing"]
    assert out["questions"][0]["id"] == "saida"
    assert out["contabil"] is False


def test_planejador_deep_merges_over_existing_plan(monkeypatch):
    # plano atual ja tem fonte.colunas; o retorno so adiciona fonte.formato -> nao pode apagar colunas
    fake = json.dumps({"questions": [], "plan": {"fonte": {"formato": "csv"}}, "contabil": False})
    monkeypatch.setattr(orchestrator, "call_agent", lambda *a, **k: fake)
    atual = {"fonte": {"colunas": [{"nome": "valor", "significado": "R$"}]}, "gatilho": "manual"}
    out = orchestrator.run_planejador([{"role": "user", "content": "x"}], atual)
    assert out["plan"]["fonte"]["formato"] == "csv"
    assert out["plan"]["fonte"]["colunas"][0]["nome"] == "valor"   # preservado pelo deep-merge
    assert out["plan"]["gatilho"] == "manual"


def test_planejador_handles_bad_json(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_agent", lambda *a, **k: "isto nao e json")
    out = orchestrator.run_planejador([{"role": "user", "content": "x"}], {})
    assert out["questions"] == []
    assert isinstance(out["missing"], list)
