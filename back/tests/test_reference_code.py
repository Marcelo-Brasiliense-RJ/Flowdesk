from app.services.reference_code import reference_for_task, REF_LOW, REF_HIGH


def test_extrato_casa_com_template_extrato_dominio():
    txt = "Ler o extrato bancario do Bradesco em PDF e gerar lancamentos para o Dominio"
    ref = reference_for_task(txt)
    assert ref is not None
    assert ref["template_key"] == "extrato-dominio"
    assert ref["score"] >= REF_HIGH
    assert "def parse_extrato" in ref["code"]


def test_tarefa_sem_relacao_tem_score_baixo():
    ref = reference_for_task("enviar um email de boas vindas para novos usuarios")
    # pode até casar algum template, mas com score abaixo do limiar de few-shot
    assert ref is None or ref["score"] < REF_LOW


def test_reference_for_task_carrega_campo_reference():
    # A1: o mecanismo passa a devolver o texto de instruções de domínio do template
    # (campo 'reference'), injetado sob demanda só quando o template casa.
    ref = reference_for_task(
        "Ler o extrato bancario do Bradesco em PDF e gerar lancamentos para o Dominio"
    )
    assert ref is not None
    assert "reference" in ref  # chave sempre presente (string vazia se o template não tiver)
