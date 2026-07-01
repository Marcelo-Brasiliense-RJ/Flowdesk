import json

from app.routers import orchestrator


def test_planejador_merges_plan_and_reports_missing(monkeypatch):
    fake = json.dumps({
        "questions": [{"id": "saida", "label": "Qual o formato de saída?",
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
    # plano atual já tem fonte.colunas; o retorno só adiciona fonte.formato -> não pode apagar colunas
    fake = json.dumps({"questions": [], "plan": {"fonte": {"formato": "csv"}}, "contabil": False})
    monkeypatch.setattr(orchestrator, "call_agent", lambda *a, **k: fake)
    atual = {"fonte": {"colunas": [{"nome": "valor", "significado": "R$"}]}, "gatilho": "manual"}
    out = orchestrator.run_planejador([{"role": "user", "content": "x"}], atual)
    assert out["plan"]["fonte"]["formato"] == "csv"
    assert out["plan"]["fonte"]["colunas"][0]["nome"] == "valor"   # preservado pelo deep-merge
    assert out["plan"]["gatilho"] == "manual"


def test_planejador_handles_bad_json(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_agent", lambda *a, **k: "isto não é json")
    out = orchestrator.run_planejador([{"role": "user", "content": "x"}], {})
    assert out["questions"] == []
    assert isinstance(out["missing"], list)


def test_planejador_recebe_contexto_e_devolve_message(monkeypatch):
    captured = {}

    def fake_call(agent_id, default, messages, **k):
        captured["msgs"] = messages
        return json.dumps({"message": "Li o extrato: 2 colunas.", "questions": [],
                           "plan": {"fonte": {"formato": "xlsx"}}, "contabil": False})

    monkeypatch.setattr(orchestrator, "call_agent", fake_call)
    out = orchestrator.run_planejador([{"role": "user", "content": "x"}], {},
                                      context="COLUNAS REAIS: Data, Valor, Histórico")
    assert out["message"] == "Li o extrato: 2 colunas."
    # o contexto dos arquivos entra como primeira mensagem, antes do histórico
    assert any("COLUNAS REAIS" in m.get("content", "") for m in captured["msgs"])
