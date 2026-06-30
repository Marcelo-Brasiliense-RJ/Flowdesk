import json

from app.routers import orchestrator


def test_nomeador_returns_name_and_description(monkeypatch):
    monkeypatch.setattr(
        orchestrator, "call_agent",
        lambda *a, **k: json.dumps({"name": "Conciliação de Razão", "description": "Concilia o razão."}),
    )
    out = orchestrator.run_nomeador({"regra_negocio": "conciliar"}, "code")
    assert out["name"] == "Conciliação de Razão"
    assert out["description"].startswith("Concilia")


def test_nomeador_handles_bad_json(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_agent", lambda *a, **k: "lixo")
    out = orchestrator.run_nomeador({}, "")
    assert out["name"] == "" and out["description"] == ""


def test_name_is_placeholder():
    assert orchestrator.name_is_placeholder("Projeto", "Criado pelo Chat") is True
    assert orchestrator.name_is_placeholder("", "qualquer") is True
    assert orchestrator.name_is_placeholder("ab", "qualquer") is True   # < 3 chars
    assert orchestrator.name_is_placeholder("Conciliação de Razão", "feita pelo usuário") is False
