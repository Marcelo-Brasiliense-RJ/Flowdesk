"""get_file(i) deve resolver 'arquivo{i+1}' por NOME (ordem dos campos do plano),
nao pela ordem em que o usuario escolheu os arquivos (que vira a ordem de insercao
no input.json). Sem isso, escolher o 2o arquivo antes do 1o alimentaria o parser
com o arquivo errado."""
import importlib.util
import json
import sys


def _load_sdk(tmp_path, monkeypatch, input_data):
    from app.services.storage import _SDK_SOURCE

    (tmp_path / "flowdesk_sdk.py").write_text(_SDK_SOURCE, encoding="utf-8")
    (tmp_path / "input.json").write_text(json.dumps(input_data), encoding="utf-8")
    monkeypatch.setenv("FLOWDESK_INPUT", str(tmp_path / "input.json"))
    monkeypatch.setenv("FLOWDESK_OUTPUT", str(tmp_path / "output.json"))
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("flowdesk_sdk", None)  # o SDK cacheia paths de env no import
    spec = importlib.util.spec_from_file_location("flowdesk_sdk", tmp_path / "flowdesk_sdk.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_get_file_resolve_por_nome_fora_de_ordem(tmp_path, monkeypatch):
    a = tmp_path / "extrato.pdf"
    a.write_text("A", encoding="utf-8")
    b = tmp_path / "plano.xlsx"
    b.write_text("B", encoding="utf-8")
    # usuario escolheu arquivo2 ANTES de arquivo1: ordem de insercao = arquivo2, arquivo1
    sdk = _load_sdk(tmp_path, monkeypatch, {"arquivo2": str(b), "arquivo1": str(a)})
    assert sdk.get_file(0) == str(a)   # arquivo1 por nome, nao o 1o valor do dict
    assert sdk.get_file(1) == str(b)   # arquivo2 por nome


def test_get_file_um_campo_cai_no_posicional(tmp_path, monkeypatch):
    a = tmp_path / "unico.xlsx"
    a.write_text("A", encoding="utf-8")
    # form de 1 arquivo usa o campo 'arquivo' (nao 'arquivo1'): cai no posicional
    sdk = _load_sdk(tmp_path, monkeypatch, {"arquivo": str(a)})
    assert sdk.get_file(0) == str(a)
    assert sdk.get_file() == str(a)
