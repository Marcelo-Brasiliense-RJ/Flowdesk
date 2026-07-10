import json
import unicodedata

from app.routers import orchestrator


def _norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


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


def test_tarefa_generica_nao_recebe_contabil_no_contexto(monkeypatch):
    # A1: para uma automação genérica, NENHUM conteúdo contábil entra no contexto
    # do Construtor (o reference contábil só é injetado quando a tarefa casa).
    captured = {}
    def fake(agent_id, prompt, messages, **k):
        captured["content"] = messages[0]["content"]
        return json.dumps({"message": "", "actions": []})
    monkeypatch.setattr(orchestrator, "call_agent", fake)
    plano = {"regra_negocio": "somar a coluna total de um arquivo CSV e gerar um resumo",
             "saida": {"contrato": "planilha com o total"}}
    orchestrator.run_construtor(plano, {}, "")
    ctx = _norm(captured["content"])
    for marcador in ["dominio", "inicia lote", "aging", "conciliac", "credito", "debito",
                     "regras_classificacao", "_classificacao"]:
        assert marcador not in ctx, f"contexto genérico vazou contábil: {marcador}"
