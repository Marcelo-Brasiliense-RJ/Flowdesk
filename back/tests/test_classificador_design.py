import json

from app.routers import orchestrator


def test_enrich_only_when_contabil(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_agent", lambda *a, **k: json.dumps({
        "plan_patch": {"saida": {"contrato": "layout Domínio: Inicia Lote reinicia por data"}},
        "perfil_updates": {}, "avisos_fiscais": ["Confirmar regime antes de gerar guia"]}))
    out = orchestrator.enrich_accounting({"contabil": True, "saida": {}}, {})
    assert "Domínio" in out["plan"]["saida"]["contrato"]
    assert out["avisos"] == ["Confirmar regime antes de gerar guia"]
    # não-contábil: não chama IA, plano inalterado
    same = orchestrator.enrich_accounting({"contabil": False}, {})
    assert same["plan"] == {"contabil": False}
    assert same["avisos"] == []


def test_enrich_never_auto_confirms_profile(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_agent", lambda *a, **k: json.dumps({
        "plan_patch": {}, "perfil_updates": {"regime": "simples", "confirmado": True},
        "avisos_fiscais": []}))
    out = orchestrator.enrich_accounting({"contabil": True}, {"confirmado": False})
    assert out["profile"]["regime"] == "simples"      # proposta entra
    assert out["profile"]["confirmado"] is False        # mas NUNCA auto-confirma
