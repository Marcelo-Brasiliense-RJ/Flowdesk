from app.routers.projects import slugify


def test_translitera_acentos_sem_apagar_letra():
    # o bug antigo virava "banc-rio" / "raz-o": acento apagado e palavra quebrada
    assert slugify("Extrato bancário", max_words=0) == "extrato-bancario"
    assert slugify("Razão", max_words=0) == "razao"
    assert slugify("Conciliação", max_words=0) == "conciliacao"


def test_remove_stopwords_e_limita_tamanho():
    assert slugify("Conciliação de Extrato e Razão") == "conciliacao-extrato-razao"
    # frase longa não vira URL gigante: no máximo 5 palavras de conteúdo
    longo = slugify("Concilie o extrato bancário com o razão casando os valores")
    assert longo == "concilie-extrato-bancario-razao-casando"
    assert len(longo.split("-")) == 5


def test_fallback_e_chave_sem_corte():
    assert slugify("") == "projeto"
    assert slugify("!!!") == "projeto"
    # max_words=0 preserva tudo (uso em chave de nó/arquivo)
    assert slugify("De Para", max_words=0) == "de-para"
