"""Loop de melhoria contínua: os fios que ligam o Treinador ao runtime.
Tudo best-effort, fora do caminho crítico."""
import json
import sys
import time
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

from app.routers import orchestrator
from app.runtime.runner import RuntimeManager
from app.services import treinador


def test_construtor_injeta_few_shot_de_exemplos_validados(monkeypatch):
    # Treinador tem um exemplo validado parecido -> ele entra no contexto do Construtor.
    monkeypatch.setattr(treinador, "examples_context",
                        lambda plan: "EXEMPLOS DE REFERÊNCIA: use este padrão XPTO.")
    captured = {}
    def fake(agent_id, prompt, messages, **k):
        captured["content"] = messages[0]["content"]
        return json.dumps({"message": "", "actions": []})
    monkeypatch.setattr(orchestrator, "call_agent", fake)
    orchestrator.run_construtor({"regra_negocio": "algo"}, {}, "")
    assert "padrão XPTO" in captured["content"]


def test_schedule_harvest_chama_harvest_project(monkeypatch):
    # o hook de colheita dispara harvest_project (em thread, best-effort).
    chamou = {}
    monkeypatch.setattr(treinador, "harvest_project",
                        lambda pid: chamou.setdefault("pid", pid))
    mgr = RuntimeManager()
    mgr._schedule_harvest(42)
    time.sleep(0.3)  # dá tempo da thread rodar
    assert chamou.get("pid") == 42


def test_schedule_harvest_engole_excecao(monkeypatch):
    # nunca propaga erro do treino para o caminho crítico.
    def boom(pid):
        raise RuntimeError("falha no treino")
    monkeypatch.setattr(treinador, "harvest_project", boom)
    mgr = RuntimeManager()
    mgr._schedule_harvest(1)  # não pode lançar
    time.sleep(0.2)
