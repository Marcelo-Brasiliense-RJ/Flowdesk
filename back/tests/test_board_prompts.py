from app.routers import ai
from app.routers import orchestrator


def test_board_mostra_prompts_reais_do_orquestrador():
    assert ai._DEFAULT_PROMPTS["planejador"] == orchestrator.PLANEJADOR_PROMPT
    assert ai._DEFAULT_PROMPTS["construtor"] == orchestrator.CONSTRUTOR_PROMPT
    assert ai._DEFAULT_PROMPTS["nomeador"] == orchestrator.NOMEADOR_PROMPT
    assert ai._DEFAULT_PROMPTS["classificador"] == orchestrator.CLASSIFICADOR_PROMPT
    # assistente e reparador continuam com os prompts reais deles
    from app.routers.chat import SYSTEM_PROMPT
    from app.routers.repair import _REPAIR_INSTR
    assert ai._DEFAULT_PROMPTS["assistente"] == SYSTEM_PROMPT
    assert ai._DEFAULT_PROMPTS["reparador"] == _REPAIR_INSTR


from pathlib import Path


def test_chat_sem_em_dash():
    txt = Path(__file__).resolve().parents[1].joinpath("app", "routers", "chat.py").read_text(encoding="utf-8")
    assert "—" not in txt   # travessao em dash proibido
