from app.routers.chat import (
    _count_input_files,
    _input_file_fields,
    _reconciled_input_fields,
)

_HELPER_2_FILES = (
    "def ler_arquivo(idx):\n"
    "    return pd.read_excel(get_file(idx))\n"
    "df_razao = ler_arquivo(0)\n"
    "df_extrato = ler_arquivo(1)\n"
)

# caso real do projeto 99: helper com 2 parametros, chamado com args extras.
_HELPER_2_ARGS = (
    "def ler_arquivo(idx, nome):\n"
    "    file = get_file(idx)\n"
    "    return pd.read_excel(file)\n"
    "def main():\n"
    "    extrato = ler_arquivo(0, 'extrato bancario')\n"
    "    razao = ler_arquivo(1, 'razao contabil')\n"
)


def test_conta_um_arquivo():
    assert _count_input_files("df = pd.read_excel(get_file())") == 1
    assert _count_input_files("x = get_file(0)") == 1
    assert _count_input_files("sem get file aqui") == 1  # default 1 campo


def test_conta_dois_arquivos():
    code = "a = pd.read_excel(get_file())\nb = pd.read_excel(get_file(1))"
    assert _count_input_files(code) == 2


def test_teto_de_seguranca():
    assert _count_input_files("get_file(99)") == 5


def test_conta_arquivos_com_helper_indireto():
    # o modelo pode embrulhar get_file num helper e chamar com indices literais
    # (caso real: conciliacao razao + extrato). Sem enxergar a indirecao, o Form
    # ganharia so 1 campo de upload e o teste com 2 arquivos ficaria impossivel.
    assert _count_input_files(_HELPER_2_FILES) == 2


def test_conta_arquivos_com_helper_de_dois_parametros():
    # helper com args extras (ler_arquivo(0, 'nome')): o indice literal nao vem colado
    # ao ')', entao o casamento por regex falhava. O AST le a aridade real.
    assert _count_input_files(_HELPER_2_ARGS) == 2


def test_labels_com_helper_de_dois_parametros():
    labels = [f["label"] for f in _input_file_fields(2, _HELPER_2_ARGS)]
    assert labels == ["Extrato", "Razao"]


def test_campos_de_arquivo():
    assert _input_file_fields(1) == [{"name": "arquivo", "label": "Arquivo", "type": "file"}]
    dois = _input_file_fields(2)
    assert [f["name"] for f in dois] == ["arquivo1", "arquivo2"]
    assert all(f["type"] == "file" for f in dois)
    assert [f["label"] for f in dois] == ["Arquivo 1", "Arquivo 2"]


def test_labels_derivam_do_nome_da_variavel():
    code = (
        "extrato = pd.read_excel(get_file(0))\n"
        "razao = pd.read_excel(get_file(1))\n"
    )
    labels = [f["label"] for f in _input_file_fields(2, code)]
    assert labels == ["Extrato", "Razao"]


def test_labels_caem_no_generico_quando_nome_nao_ajuda():
    code = "df = pd.read_excel(get_file(0))\ndata = pd.read_excel(get_file(1))"
    labels = [f["label"] for f in _input_file_fields(2, code)]
    assert labels == ["Arquivo 1", "Arquivo 2"]


def test_labels_com_helper_indireto():
    # rotulo vem do nome da variavel no ponto de chamada do helper, nao do get_file
    # interno (que usa a variavel generica do parametro).
    labels = [f["label"] for f in _input_file_fields(2, _HELPER_2_FILES)]
    assert labels == ["Razao", "Extrato"]


def test_reconcilia_form_defasado_de_1_para_2():
    # caso do projeto ja montado com 1 campo cujo script passou a ler 2 arquivos.
    old = [{"name": "arquivo", "type": "file", "label": "Arquivo"}]
    novos = _reconciled_input_fields(old, _HELPER_2_FILES)
    assert [f["name"] for f in novos] == ["arquivo1", "arquivo2"]
    assert [f["label"] for f in novos] == ["Razao", "Extrato"]


def test_reconcilia_no_op_quando_ja_bate():
    # ja com os 2 campos certos -> None (nao regrava o Form a toa).
    ja_certo = _input_file_fields(2, _HELPER_2_FILES)
    assert _reconciled_input_fields(ja_certo, _HELPER_2_FILES) is None


def test_reconcilia_ignora_script_sem_arquivo():
    # script sem get_file nao deve injetar campo de upload num form de campos de texto.
    old = [{"name": "mes", "type": "text", "label": "Mês"}]
    assert _reconciled_input_fields(old, "x = get_input()['mes']") is None


def test_reconcilia_preserva_campos_nao_arquivo():
    old = [
        {"name": "arquivo", "type": "file", "label": "Arquivo"},
        {"name": "mes", "type": "text", "label": "Mês"},
    ]
    novos = _reconciled_input_fields(old, _HELPER_2_FILES)
    assert [f["name"] for f in novos] == ["arquivo1", "arquivo2", "mes"]


def test_input_file_fields_usa_papeis_do_plano():
    # papel do plano (analyze) vence o rotulo derivado do codigo
    code = "ext = get_file(0)\npl = get_file(1)\n"
    plan = [
        {"role": "extrato", "label": "Extrato bancario"},
        {"role": "plano_contas", "label": "Plano de contas"},
        {"role": "modelo", "label": "Modelo Dominio"},
    ]
    fields = _input_file_fields(3, code, plan)
    assert [f["name"] for f in fields] == ["arquivo1", "arquivo2", "arquivo3"]
    assert [f["label"] for f in fields] == ["Extrato bancario", "Plano de contas", "Modelo Dominio"]


def test_input_file_fields_sem_plano_mantem_comportamento():
    # plan_files ausente => rotulos derivam do codigo, como antes
    code = "extrato = pd.read_excel(get_file(0))\nrazao = pd.read_excel(get_file(1))\n"
    assert [f["label"] for f in _input_file_fields(2, code)] == ["Extrato", "Razao"]


def test_input_fields_dimensiona_por_max_plano_codigo():
    from app.routers.wizard import _input_fields
    code = "ext = get_file(0)\npl = get_file(1)\n"  # codigo le 2
    inp = {"kind": "file", "files": [
        {"role": "extrato", "label": "Extrato"},
        {"role": "plano", "label": "Plano"},
        {"role": "modelo", "label": "Modelo"},
    ]}  # plano pede 3
    fields = _input_fields(inp, code)
    assert len(fields) == 3            # max(3, 2)
    assert fields[0]["label"] == "Extrato"
    assert fields[2]["label"] == "Modelo"
