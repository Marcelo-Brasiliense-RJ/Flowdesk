import types

import pytest

from app.services import ai_call


def _fake_client(sink):
    def resp_create(**kw):
        sink["path"] = "responses"
        sink["kw"] = kw
        return types.SimpleNamespace(output_text="TEXTO-RACIOCINIO")

    def chat_create(**kw):
        sink["path"] = "chat"
        sink["kw"] = kw
        if kw.get("stream"):
            def ev(txt):
                delta = types.SimpleNamespace(content=txt)
                return types.SimpleNamespace(choices=[types.SimpleNamespace(delta=delta)])
            return [ev("oi "), ev("mundo")]
        msg = types.SimpleNamespace(content="TEXTO-CHAT")
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    return types.SimpleNamespace(
        responses=types.SimpleNamespace(create=resp_create),
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=chat_create)),
    )


@pytest.mark.parametrize("model", ["gpt-5", "gpt-5.5", "gpt-5.3-codex", "o3-mini", "o4-mini"])
def test_is_reasoning_true(model):
    assert ai_call.is_reasoning(model) is True


@pytest.mark.parametrize("model", ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"])
def test_is_reasoning_false(model):
    assert ai_call.is_reasoning(model) is False


def test_complete_reasoning_usa_responses_sem_temperature(monkeypatch):
    sink = {}
    monkeypatch.setattr(ai_call, "_client", lambda: _fake_client(sink))
    out = ai_call.complete("gpt-5.5", [{"role": "user", "content": "x"}],
                           temperature=0.2, json_mode=True)
    assert sink["path"] == "responses"
    assert "temperature" not in sink["kw"]
    assert "response_format" not in sink["kw"]
    assert sink["kw"]["input"] == [{"role": "user", "content": "x"}]
    assert out == "TEXTO-RACIOCINIO"


def test_complete_chat_mantem_temperature_e_json(monkeypatch):
    sink = {}
    monkeypatch.setattr(ai_call, "_client", lambda: _fake_client(sink))
    out = ai_call.complete("gpt-4o-mini", [{"role": "user", "content": "x"}],
                           temperature=0.0, json_mode=True)
    assert sink["path"] == "chat"
    assert sink["kw"]["temperature"] == 0.0
    assert sink["kw"]["response_format"] == {"type": "json_object"}
    assert out == "TEXTO-CHAT"


def test_complete_reasoning_ignora_max_tokens_pequeno(monkeypatch):
    # modelos de raciocinio gastam tokens "pensando"; um teto pequeno (ex.: 20 do
    # nomeador) zeraria a resposta, entao nao deve ser repassado.
    sink = {}
    monkeypatch.setattr(ai_call, "_client", lambda: _fake_client(sink))
    ai_call.complete("gpt-5", [{"role": "user", "content": "x"}], max_tokens=20)
    assert "max_output_tokens" not in sink["kw"]


def test_stream_text_reasoning_entrega_de_uma_vez(monkeypatch):
    sink = {}
    monkeypatch.setattr(ai_call, "_client", lambda: _fake_client(sink))
    chunks = list(ai_call.stream_text("gpt-5.5", [{"role": "user", "content": "x"}]))
    assert sink["path"] == "responses"
    assert "".join(chunks) == "TEXTO-RACIOCINIO"


def test_stream_text_chat_faz_streaming_por_delta(monkeypatch):
    sink = {}
    monkeypatch.setattr(ai_call, "_client", lambda: _fake_client(sink))
    chunks = list(ai_call.stream_text("gpt-4o-mini", [{"role": "user", "content": "x"}]))
    assert sink["path"] == "chat"
    assert sink["kw"]["stream"] is True
    assert "".join(chunks) == "oi mundo"


def test_parse_json_limpo():
    assert ai_call.parse_json('{"a": 1}') == {"a": 1}


def test_parse_json_remove_cerca_de_codigo():
    # modelos de raciocinio, sem response_format, as vezes cercam com ```json
    txt = '```json\n{"diagnosis": "ok", "fixed_code": "x"}\n```'
    assert ai_call.parse_json(txt) == {"diagnosis": "ok", "fixed_code": "x"}


def test_parse_json_extrai_bloco_no_meio_de_texto():
    assert ai_call.parse_json('Claro, aqui esta: {"a": 1} pronto') == {"a": 1}


def test_parse_json_invalido_ou_vazio_retorna_dict_vazio():
    assert ai_call.parse_json("isso nao e json") == {}
    assert ai_call.parse_json("") == {}
    assert ai_call.parse_json(None) == {}
