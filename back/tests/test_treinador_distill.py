"""Destilação por limiar: ao juntar exemplos, o Treinador propõe prompts melhores
(pending, aprovação humana). Tudo best-effort."""
import sys
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

from app.services import treinador


def test_maybe_distill_so_roda_no_limiar(monkeypatch, tmp_path):
    monkeypatch.setattr(treinador, "_DIR", tmp_path / "treinador")
    chamou = {"n": 0}
    monkeypatch.setattr(treinador, "distill", lambda agent_ids: chamou.__setitem__("n", chamou["n"] + 1))
    # abaixo do limiar: não destila
    treinador._save(treinador._meta_path(), {"new_examples": treinador.DISTILL_THRESHOLD - 1})
    treinador.maybe_distill(["construtor"])
    assert chamou["n"] == 0
    # no limiar: destila e zera o contador
    treinador._save(treinador._meta_path(), {"new_examples": treinador.DISTILL_THRESHOLD})
    treinador.maybe_distill(["construtor"])
    assert chamou["n"] == 1
    assert treinador._load(treinador._meta_path()).get("new_examples") == 0


def test_distill_grava_proposta_pending_por_agente(monkeypatch, tmp_path):
    monkeypatch.setattr(treinador, "_DIR", tmp_path / "treinador")
    treinador._save(treinador._examples_path(),
                    {"items": [{"plan": {"contabil": True}, "code": "x=1"}]})
    monkeypatch.setattr(treinador, "_distill_agent",
                        lambda agent_id, exemplos, repairs: {"proposed_prompt": "melhor",
                                                             "rationale": "porque sim"})
    treinador.distill(["construtor"])
    props = treinador.list_proposals()
    assert len(props) == 1
    assert props[0]["agent_id"] == "construtor"
    assert props[0]["status"] == "pending"
    assert props[0]["proposed_prompt"] == "melhor"


def test_resolve_proposal_aprova_e_aplica(monkeypatch, tmp_path):
    monkeypatch.setattr(treinador, "_DIR", tmp_path / "treinador")
    aplicou = {}
    import app.services.ai_config as ai_config
    monkeypatch.setattr(ai_config, "apply_prompt",
                        lambda agent_id, prompt: aplicou.update({agent_id: prompt}))
    treinador._save(treinador._proposals_path(), {"items": [
        {"id": "p1", "agent_id": "construtor", "proposed_prompt": "novo", "status": "pending"}]})
    ok = treinador.resolve_proposal("p1", approved=True)
    assert ok
    assert aplicou["construtor"] == "novo"
    assert treinador.list_proposals(status="approved")[0]["id"] == "p1"
