import types
import app.routers.repair as repair


class _FakeCompletions:
    def __init__(self, sink): self.sink = sink
    def create(self, **kw):
        self.sink["model"] = kw["model"]
        msg = types.SimpleNamespace(content='{"diagnosis":"d","change_summary":"c","fixed_code":"x"}')
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])


def test_repair_usa_modelo_do_reparador(monkeypatch):
    sink = {}
    fake_client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=_FakeCompletions(sink)))
    monkeypatch.setattr(repair, "OpenAI", lambda **kw: fake_client, raising=False)
    monkeypatch.setattr(repair.ai_config, "get_agent_model", lambda a: f"modelo-de-{a}")
    # neutraliza acesso a DB/arquivos
    monkeypatch.setattr(repair, "_stage_source", lambda db, pid, st: None)
    monkeypatch.setattr(repair, "_execution_context", lambda e: "")
    monkeypatch.setattr(repair, "_attachment_context", lambda pid, paths: "")
    monkeypatch.setattr(repair, "_plan_profile_context", lambda plan, prof: "")
    db = types.SimpleNamespace(get=lambda model, _id: None)
    project = types.SimpleNamespace(id=1, plan={}, accounting_profile={})
    stage = types.SimpleNamespace()
    repair.run_repair(db, project, stage, "exec-1", None)
    assert sink["model"] == "modelo-de-reparador"
