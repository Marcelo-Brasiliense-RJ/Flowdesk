from app.routers.chat import _count_input_files, _input_file_fields


def test_conta_um_arquivo():
    assert _count_input_files("df = pd.read_excel(get_file())") == 1
    assert _count_input_files("x = get_file(0)") == 1
    assert _count_input_files("sem get file aqui") == 1  # default 1 campo


def test_conta_dois_arquivos():
    code = "a = pd.read_excel(get_file())\nb = pd.read_excel(get_file(1))"
    assert _count_input_files(code) == 2


def test_teto_de_seguranca():
    assert _count_input_files("get_file(99)") == 5


def test_campos_de_arquivo():
    assert _input_file_fields(1) == [{"name": "arquivo", "label": "Arquivo", "type": "file"}]
    dois = _input_file_fields(2)
    assert [f["name"] for f in dois] == ["arquivo1", "arquivo2"]
    assert all(f["type"] == "file" for f in dois)
    assert [f["label"] for f in dois] == ["Arquivo 1", "Arquivo 2"]
