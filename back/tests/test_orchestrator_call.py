from unittest.mock import PropertyMock, patch

from app.routers import orchestrator
from app.services import ai_call
from app.services.ai_guard import SECURITY_PREAMBLE


def test_call_agent_uses_agent_prompt_and_model(monkeypatch):
    captured = {}

    class FakeResp:
        choices = [type("C", (), {"message": type("M", (), {"content": "oi"})()})()]

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    captured.update(kw)
                    return FakeResp()

    monkeypatch.setattr(ai_call, "_client", lambda: FakeClient())
    with patch.object(type(orchestrator.settings), "ai_enabled", new_callable=PropertyMock) as mock_prop:
        mock_prop.return_value = True
        monkeypatch.setattr(orchestrator.ai_config, "get_agent_model", lambda a: "gpt-test")
        monkeypatch.setattr(orchestrator.ai_config, "get_temp", lambda a, default=0.2: 0.0)
        monkeypatch.setattr(orchestrator.ai_config, "get_prompt", lambda a, d: "PROMPT-PLAN")

        out = orchestrator.call_agent("planejador", "def", [{"role": "user", "content": "x"}])
        assert out == "oi"
        assert captured["model"] == "gpt-test"
        assert captured["temperature"] == 0.0
        # preâmbulo de segurança sempre à frente, depois o prompt do agente, depois o user
        assert captured["messages"][0] == {"role": "system", "content": SECURITY_PREAMBLE}
        assert captured["messages"][1] == {"role": "system", "content": "PROMPT-PLAN"}
        assert captured["messages"][2] == {"role": "user", "content": "x"}


def test_call_agent_disabled_returns_empty(monkeypatch):
    with patch.object(type(orchestrator.settings), "ai_enabled", new_callable=PropertyMock) as mock_prop:
        mock_prop.return_value = False
        assert orchestrator.call_agent("planejador", "def", [{"role": "user", "content": "x"}]) == ""
