import json

from app.routers import orchestrator


def test_construtor_consumes_plan_and_returns_actions(monkeypatch):
    captured = {}

    def fake_call(agent_id, default, messages, **k):
        captured["agent"] = agent_id
        captured["sees_plan"] = any("regra_negocio" in m["content"] for m in messages)
        return json.dumps({"message": "feito", "actions": [
            {"kind": "create_file", "title": "x", "path": "p.py", "content": "set_output({})"}]})

    monkeypatch.setattr(orchestrator, "call_agent", fake_call)
    out = orchestrator.run_construtor(
        {"regra_negocio": "somar por cliente", "saida": {"formato": "xlsx"}}, {}, "ctx")
    assert captured["agent"] == "construtor"
    assert captured["sees_plan"] is True
    assert out["message"] == "feito"
    assert out["actions"][0]["kind"] == "create_file"


def test_construtor_includes_profile_when_contabil(monkeypatch):
    captured = {}

    def fake_call(agent_id, default, messages, **k):
        captured["text"] = " ".join(m["content"] for m in messages)
        return json.dumps({"message": "ok", "actions": []})

    monkeypatch.setattr(orchestrator, "call_agent", fake_call)
    orchestrator.run_construtor(
        {"contabil": True, "regra_negocio": "classificar"},
        {"regime": "simples", "erp_destino": "Domínio"}, "")
    assert "Domínio" in captured["text"]   # perfil entrou no contexto
    assert "simples" in captured["text"]


def test_construtor_handles_bad_json(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_agent", lambda *a, **k: "lixo")
    out = orchestrator.run_construtor({"regra_negocio": "x"}, {}, "")
    assert out["message"] == "" and out["actions"] == []
