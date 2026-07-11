import types
from app.routers import orchestrator
from app.services import ai_call


def _fake_client(sink):
    def resp_create(**kw):
        sink["path"] = "responses"; sink["kw"] = kw
        return types.SimpleNamespace(output_text='{"ok":1}')
    def chat_create(**kw):
        sink["path"] = "chat"; sink["kw"] = kw
        msg = types.SimpleNamespace(content='{"ok":2}')
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])
    return types.SimpleNamespace(
        responses=types.SimpleNamespace(create=resp_create),
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=chat_create)),
    )


def test_codex_vai_para_responses(monkeypatch):
    sink = {}
    monkeypatch.setattr(ai_call, "_client", lambda: _fake_client(sink))
    monkeypatch.setattr(orchestrator.ai_config, "get_agent_model", lambda a: "gpt-5.3-codex")
    monkeypatch.setattr(orchestrator.ai_config, "get_prompt", lambda a, d: "sys")
    out = orchestrator.call_agent("construtor", "sys", [{"role": "user", "content": "oi"}], json_mode=True)
    assert sink["path"] == "responses"
    assert "temperature" not in sink["kw"]
    # Construtor troca profundidade por latência: esforço medium na Responses API
    assert sink["kw"]["reasoning"] == {"effort": "medium"}
    assert out == '{"ok":1}'


def test_chat_model_continua_em_chat(monkeypatch):
    sink = {}
    monkeypatch.setattr(ai_call, "_client", lambda: _fake_client(sink))
    monkeypatch.setattr(orchestrator.ai_config, "get_agent_model", lambda a: "gpt-4o-mini")
    monkeypatch.setattr(orchestrator.ai_config, "get_prompt", lambda a, d: "sys")
    monkeypatch.setattr(orchestrator.ai_config, "get_temp", lambda a: 0.2)
    out = orchestrator.call_agent("planejador", "sys", [{"role": "user", "content": "oi"}], json_mode=True)
    assert sink["path"] == "chat"
    assert sink["kw"]["response_format"] == {"type": "json_object"}
    assert out == '{"ok":2}'
