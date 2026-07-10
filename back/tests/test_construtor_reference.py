import json
from app.routers import orchestrator


def _plan_extrato():
    return {"regra_negocio": "extrato bancario Bradesco em PDF para lancamentos do Dominio",
            "saida": {"contrato": "layout Dominio"}}


def test_semente_deterministica_em_casamento_claro(monkeypatch):
    # o modelo devolve um script "errado"; a semente deve sobrescrever com o template
    monkeypatch.setattr(orchestrator, "call_agent", lambda *a, **k: json.dumps({
        "message": "ok",
        "actions": [{"kind": "create_file", "path": "x.py", "content": "print('errado')"}],
    }))
    out = orchestrator.run_construtor(_plan_extrato(), {}, "")
    py = next(a for a in out["actions"] if a["path"].endswith(".py"))
    assert "def parse_extrato" in py["content"]      # veio do template extrato-dominio
    assert "print('errado')" not in py["content"]


def test_few_shot_injeta_referencia_no_prompt(monkeypatch):
    captured = {}
    def fake(agent_id, prompt, messages, **k):
        captured["content"] = messages[0]["content"]
        return json.dumps({"message": "", "actions": []})
    monkeypatch.setattr(orchestrator, "call_agent", fake)
    orchestrator.run_construtor(_plan_extrato(), {}, "")
    assert "IMPLEMENTAÇÃO DE REFERÊNCIA PROVADA" in captured["content"]
    assert "def parse_extrato" in captured["content"]


def test_reference_de_dominio_injetado_quando_presente(monkeypatch):
    # A1: quando o template casado traz instruções de domínio (reference),
    # elas entram no contexto do Construtor sob demanda.
    monkeypatch.setattr(orchestrator, "reference_for_task", lambda txt: {
        "template_key": "extrato-dominio",
        "code": "# codigo de referencia",
        "reference": "REGRAS DO DOMINIO XYZ: a coluna Inicia Lote reinicia a cada dia.",
        "score": 4,
    })
    captured = {}
    def fake(agent_id, prompt, messages, **k):
        captured["content"] = messages[0]["content"]
        return json.dumps({"message": "", "actions": []})
    monkeypatch.setattr(orchestrator, "call_agent", fake)
    orchestrator.run_construtor(_plan_extrato(), {}, "")
    assert "Inicia Lote reinicia a cada dia" in captured["content"]
