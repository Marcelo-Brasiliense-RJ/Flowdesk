import sys
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

from app.routers.chat import _is_build_intent


def test_prompt_descritivo_nao_constroi():
    # T1/T3/T4: verbo no meio da frase descreve a tarefa, deve ABRIR entrevista
    assert _is_build_intent("Tenho uma planilha de vendas. Quero o total por produto, gerando uma planilha de saída.") is False
    assert _is_build_intent("Concilie este razão contábil e gere um resumo com os totais.") is False
    assert _is_build_intent("Classifique cada título por faixa de atraso e some o valor por faixa.") is False


def test_prefixo_respostas_constroi():
    assert _is_build_intent("Respostas da entrevista: fonte=xlsx; saida=planilha") is True


def test_comando_explicito_constroi():
    assert _is_build_intent("pode montar agora") is True
    assert _is_build_intent("Monte o app") is True
    assert _is_build_intent("finaliza isso") is True
