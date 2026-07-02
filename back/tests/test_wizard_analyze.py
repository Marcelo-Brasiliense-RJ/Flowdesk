from app.routers import wizard
from app.config import settings


def test_instrucao_pede_lista_de_arquivos():
    instr = wizard._ANALYZE_INSTR
    assert '"files"' in instr
    assert "role" in instr and "get_file(0)" in instr


def test_fallback_sem_ia_tem_chave_files(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    plan = wizard._analyze_prompt(None, 1, "somar a planilha enviada", None)
    assert plan["input"]["kind"] == "file"
    assert isinstance(plan["input"]["files"], list)
