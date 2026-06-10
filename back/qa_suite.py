"""FlowDesk end-to-end QA suite — exercises every module against a live server.

Run the backend first:  uvicorn main:app --port 8000
Then:  python qa_suite.py
Creates only 'QA …' projects and deletes them at the end.
"""
import asyncio
import json
import time

import httpx

BASE = "http://127.0.0.1:8000"
RESULTS = []
CREATED_PROJECTS = []


def check(name, cond, detail=""):
    RESULTS.append((bool(cond), name, detail))
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not cond else ""))


def section(t):
    print(f"\n=== {t} ===")


def login(c):
    r = c.post(f"{BASE}/api/auth/login",
               json={"email": "admin@irko.com.br", "password": "flowdesk123"})
    return r.json()["access_token"]


def new_project(c, H, name):
    p = c.post(f"{BASE}/api/projects", headers=H, json={"name": name}).json()
    CREATED_PROJECTS.append(p["id"])
    return p


def poll(c, H, pid, exid, timeout=20):
    for _ in range(timeout):
        time.sleep(1)
        ex = c.get(f"{BASE}/api/projects/{pid}/executions/{exid}", headers=H).json()
        if ex.get("status") in ("success", "error"):
            return ex
    return ex


def make_script(c, H, pid, name, code, timeout=120):
    s = c.post(f"{BASE}/api/projects/{pid}/stages", headers=H,
               json={"type": "script", "name": name, "timeout_seconds": timeout}).json()
    c.put(f"{BASE}/api/projects/{pid}/files", headers=H,
          json={"path": s["entry_file"], "content": code})
    return s


def run_and_poll(c, H, pid, sid, payload):
    ex = c.post(f"{BASE}/api/projects/{pid}/stages/{sid}/run", headers=H, json=payload).json()
    return poll(c, H, pid, ex["id"])


def main():
    c = httpx.Client(timeout=120)

    section("Auth")
    bad = c.post(f"{BASE}/api/auth/login", json={"email": "admin@irko.com.br", "password": "x"})
    check("login senha errada -> 401", bad.status_code == 401)
    tok = login(c)
    H = {"Authorization": f"Bearer {tok}"}
    me = c.get(f"{BASE}/api/auth/me", headers=H)
    check("/me autenticado", me.status_code == 200 and me.json()["email"] == "admin@irko.com.br")
    noauth = c.get(f"{BASE}/api/projects")
    check("listar projetos sem token -> 401", noauth.status_code == 401)
    check("health ai_enabled presente", "ai_enabled" in c.get(f"{BASE}/api/health").json())

    section("Projetos e pastas")
    p1 = new_project(c, H, "QA Base")
    p1b = new_project(c, H, "QA Base")
    check("subdominio unico", p1["subdomain"] != p1b["subdomain"], f"{p1['subdomain']} vs {p1b['subdomain']}")
    lst = c.get(f"{BASE}/api/projects", headers=H).json()
    check("projeto aparece na lista", any(x["id"] == p1["id"] for x in lst))
    check("get projeto inexistente -> 404",
          c.get(f"{BASE}/api/projects/999999", headers=H).status_code == 404)
    fold = c.post(f"{BASE}/api/folders", headers=H, json={"name": "QA Folder"}).json()
    check("criar pasta", "id" in fold)

    section("Stages e edges")
    pid = p1["id"]
    f_in = c.post(f"{BASE}/api/projects/{pid}/stages", headers=H,
                  json={"type": "form", "name": "QA Form"}).json()
    hook = c.post(f"{BASE}/api/projects/{pid}/stages", headers=H,
                  json={"type": "hook", "name": "QA Hook"}).json()
    job = c.post(f"{BASE}/api/projects/{pid}/stages", headers=H,
                 json={"type": "job", "name": "QA Job"}).json()
    bad_type = c.post(f"{BASE}/api/projects/{pid}/stages", headers=H,
                      json={"type": "banana", "name": "X"})
    check("tipo de no invalido -> 400", bad_type.status_code == 400)
    s1 = c.post(f"{BASE}/api/projects/{pid}/stages", headers=H, json={"type": "script", "name": "Dup"}).json()
    s2 = c.post(f"{BASE}/api/projects/{pid}/stages", headers=H, json={"type": "script", "name": "Dup"}).json()
    check("keys unicas para nomes iguais", s1["key"] != s2["key"], f"{s1['key']} / {s2['key']}")
    patched = c.patch(f"{BASE}/api/projects/{pid}/stages/{f_in['id']}", headers=H,
                      json={"pos_x": 123.0}).json()
    check("patch posicao do no", patched["pos_x"] == 123.0)
    c.post(f"{BASE}/api/projects/{pid}/edges", headers=H,
           json={"source_stage_id": f_in["id"], "target_stage_id": s1["id"], "variable_label": "v"})
    e2 = c.post(f"{BASE}/api/projects/{pid}/edges", headers=H,
                json={"source_stage_id": s1["id"], "target_stage_id": hook["id"]}).json()
    edges = c.get(f"{BASE}/api/projects/{pid}/edges", headers=H).json()
    check("2 edges criados", len(edges) == 2)
    c.delete(f"{BASE}/api/projects/{pid}/edges/{e2['id']}", headers=H)
    check("edge removido", len(c.get(f"{BASE}/api/projects/{pid}/edges", headers=H).json()) == 1)
    c.delete(f"{BASE}/api/projects/{pid}/stages/{job['id']}", headers=H)
    check("stage removido", all(s["id"] != job["id"]
          for s in c.get(f"{BASE}/api/projects/{pid}/stages", headers=H).json()))

    section("Arquivos de codigo (Monaco)")
    c.put(f"{BASE}/api/projects/{pid}/files", headers=H, json={"path": "qa.py", "content": "a=1"})
    files = c.get(f"{BASE}/api/projects/{pid}/files", headers=H).json()
    check("arquivo criado", any(f["path"] == "qa.py" for f in files))
    c.put(f"{BASE}/api/projects/{pid}/files", headers=H, json={"path": "qa.py", "content": "a=2"})
    files = c.get(f"{BASE}/api/projects/{pid}/files", headers=H).json()
    check("upsert atualiza conteudo", any(f["path"] == "qa.py" and f["content"] == "a=2" for f in files))
    c.delete(f"{BASE}/api/projects/{pid}/files", headers=H, params={"path": "qa.py"})
    check("arquivo removido", not any(f["path"] == "qa.py"
          for f in c.get(f"{BASE}/api/projects/{pid}/files", headers=H).json()))

    section("Runtime de scripts (subprocesso)")
    ok = make_script(c, H, pid, "QA OK",
                     "from flowdesk_sdk import get_input,set_output\n"
                     "d=get_input()\nset_output({'soma': d.get('a',0)+d.get('b',0)})\n")
    ex = run_and_poll(c, H, pid, ok["id"], {"a": 2, "b": 3})
    check("script sucesso", ex["status"] == "success" and ex["output_data"].get("soma") == 5,
          f"status={ex['status']} out={ex.get('output_data')}")
    err = make_script(c, H, pid, "QA Err", "raise ValueError('boom QA')\n")
    ex = run_and_poll(c, H, pid, err["id"], {})
    check("script erro -> status error + stderr", ex["status"] == "error" and "boom QA" in ex["stderr"],
          f"status={ex['status']}")
    tmo = make_script(c, H, pid, "QA Timeout", "import time\ntime.sleep(5)\n", timeout=1)
    ex = run_and_poll(c, H, pid, tmo["id"], {})
    check("script timeout -> error", ex["status"] == "error" and "limite" in ex["stderr"].lower(),
          f"status={ex['status']} stderr={ex['stderr'][:60]}")

    section("Variaveis de ambiente + injecao no subprocesso")
    c.put(f"{BASE}/api/projects/{pid}/env", headers=H,
          json={"key": "QA_SECRET", "value": "hello123", "secret": True})
    envs = c.get(f"{BASE}/api/projects/{pid}/env", headers=H).json()
    check("env var listada", any(e["key"] == "QA_SECRET" for e in envs))
    rdenv = make_script(c, H, pid, "QA Env",
                        "import os\nfrom flowdesk_sdk import set_output\n"
                        "set_output({'v': os.environ.get('QA_SECRET','missing')})\n")
    ex = run_and_poll(c, H, pid, rdenv["id"], {})
    check("env injetada no subprocesso", ex["output_data"].get("v") == "hello123",
          f"out={ex.get('output_data')}")
    eid = [e["id"] for e in envs if e["key"] == "QA_SECRET"][0]
    c.delete(f"{BASE}/api/projects/{pid}/env/{eid}", headers=H)
    check("env removida", not any(e["key"] == "QA_SECRET"
          for e in c.get(f"{BASE}/api/projects/{pid}/env", headers=H).json()))

    section("Chaves de API / papeis / tabelas")
    k = c.post(f"{BASE}/api/projects/{pid}/api-keys", headers=H, params={"name": "QA Key"}).json()
    check("api key gerada (fdk_)", k["token"].startswith("fdk_"))
    c.delete(f"{BASE}/api/projects/{pid}/api-keys/{k['id']}", headers=H)
    role = c.post(f"{BASE}/api/projects/{pid}/roles", headers=H,
                  json={"name": "QA Role", "description": "d"}).json()
    check("papel criado", role["name"] == "QA Role")
    tbl = c.post(f"{BASE}/api/projects/{pid}/tables", headers=H, params={"name": "QA Tab"}).json()
    check("tabela interna criada", tbl["name"] == "QA Tab")

    section("Builds / publicacao (apenas 1 'No ar')")
    b1 = c.post(f"{BASE}/api/projects/{pid}/publish", headers=H).json()
    b2 = c.post(f"{BASE}/api/projects/{pid}/publish", headers=H).json()
    builds = c.get(f"{BASE}/api/projects/{pid}/builds", headers=H).json()
    live = [b for b in builds if b["status"] == "live"]
    check("2 builds, apenas 1 live", len(builds) >= 2 and len(live) == 1 and live[0]["id"] == b2["id"])
    c.post(f"{BASE}/api/projects/{pid}/builds/{b1['id']}/activate", headers=H)
    builds = c.get(f"{BASE}/api/projects/{pid}/builds", headers=H).json()
    live = [b for b in builds if b["status"] == "live"]
    check("ativar build antigo mantem 1 live", len(live) == 1 and live[0]["id"] == b1["id"])

    section("File manager (disco) + path traversal")
    c.post(f"{BASE}/api/projects/{pid}/fs/upload", headers=H, data={"path": "uploads"},
           files={"file": ("qa.txt", b"conteudo qa")})
    br = c.get(f"{BASE}/api/projects/{pid}/fs", headers=H, params={"path": "uploads"}).json()
    check("upload aparece no fs", any(e["name"] == "qa.txt" for e in br["entries"]))
    c.post(f"{BASE}/api/projects/{pid}/fs/folder", headers=H, data={"path": "uploads/sub"})
    c.post(f"{BASE}/api/projects/{pid}/fs/rename", headers=H,
           data={"path": "uploads/qa.txt", "new_name": "qa2.txt"})
    br = c.get(f"{BASE}/api/projects/{pid}/fs", headers=H, params={"path": "uploads"}).json()
    check("renomear arquivo", any(e["name"] == "qa2.txt" for e in br["entries"]))
    dl = c.get(f"{BASE}/api/projects/{pid}/fs/download", headers=H, params={"path": "uploads/qa2.txt"})
    check("download retorna conteudo", dl.status_code == 200 and dl.content == b"conteudo qa")
    trav = c.get(f"{BASE}/api/projects/{pid}/fs", headers=H, params={"path": "../../"})
    check("path traversal bloqueado -> 400", trav.status_code == 400, f"status={trav.status_code}")
    c.request("DELETE", f"{BASE}/api/projects/{pid}/fs", headers=H, params={"path": "uploads/qa2.txt"})
    br = c.get(f"{BASE}/api/projects/{pid}/fs", headers=H, params={"path": "uploads"}).json()
    check("excluir arquivo", not any(e["name"] == "qa2.txt" for e in br["entries"]))

    section("Controle de acesso (app publicado)")
    PWD = "flowdesk123"
    pa = new_project(c, H, "QA Acesso")
    pasub = pa["subdomain"]
    deny = c.post(f"{BASE}/api/app/{pasub}/login", data={"email": "ana@irko.com.br", "password": PWD})
    check("whitelist sem membro -> 403", deny.status_code == 403)
    c.post(f"{BASE}/api/projects/{pa['id']}/members", headers=H,
           json={"email": "ana@irko.com.br", "roles": ["User"]})
    allow = c.post(f"{BASE}/api/app/{pasub}/login", data={"email": "ana@irko.com.br", "password": PWD})
    check("whitelist com membro -> 200", allow.status_code == 200)
    c.put(f"{BASE}/api/projects/{pa['id']}/access-policy", headers=H,
          json={"access_mode": "domain", "allowed_domain": "irko.com.br"})
    check("dominio permite @irko.com.br",
          c.post(f"{BASE}/api/app/{pasub}/login", data={"email": "bruno@irko.com.br", "password": PWD}).status_code == 200)
    check("email nao autorizado bloqueado",
          c.post(f"{BASE}/api/app/{pasub}/login", data={"email": "x@gmail.com", "password": PWD}).status_code in (401, 403))
    check("submit sem token -> 401",
          c.post(f"{BASE}/api/app/{pasub}/stages/1/submit", data={}).status_code == 401)

    section("Segurança (correções da revisão)")
    # #1 login publicado exige credencial
    check("login publicado sem senha -> 401/422",
          c.post(f"{BASE}/api/app/{pasub}/login", data={"email": "ana@irko.com.br"}).status_code in (401, 422))
    check("login publicado senha errada -> 401",
          c.post(f"{BASE}/api/app/{pasub}/login", data={"email": "bruno@irko.com.br", "password": "errada"}).status_code == 401)
    # #2 traversal no filename do upload -> salvo como basename
    up = c.post(f"{BASE}/api/projects/{pid}/fs/upload", headers=H, data={"path": "uploads"},
                files={"file": ("../../../pwned.txt", b"x")}).json()
    check("upload sanitiza filename (basename)", up.get("name") == "pwned.txt", f"name={up.get('name')}")
    br = c.get(f"{BASE}/api/projects/{pid}/fs", headers=H, params={"path": "uploads"}).json()
    check("arquivo de traversal ficou em uploads", any(e["name"] == "pwned.txt" for e in br["entries"]))
    # #5 path de SourceFile com traversal -> 400
    trav = c.put(f"{BASE}/api/projects/{pid}/files", headers=H,
                 json={"path": "../../etc/x.py", "content": "x"})
    check("source file com traversal -> 400", trav.status_code == 400, f"status={trav.status_code}")
    # #4 WS sem token -> rejeitado
    try:
        async def ws_noauth():
            import websockets
            async with websockets.connect(f"ws://127.0.0.1:8000/ws/projects/{pid}") as ws:
                await asyncio.wait_for(ws.recv(), timeout=4)
            return "recebeu"
        asyncio.run(ws_noauth())
        check("WS sem token rejeitado", False, "conectou sem token")
    except Exception:
        check("WS sem token rejeitado", True)

    section("Fluxo publicado ponta-a-ponta (Form->Script->Form)")
    pf = new_project(c, H, "QA Fluxo")
    fid = c.post(f"{BASE}/api/projects/{pf['id']}/stages", headers=H, json={
        "type": "form", "name": "Entrada",
        "config": {"mode": "input", "fields": [{"name": "n", "label": "n", "type": "text"}]}}).json()
    sc = make_script(c, H, pf["id"], "Dobrar",
                     "from flowdesk_sdk import get_input,set_output\n"
                     "d=get_input()\nset_output({'dobro': int(d.get('n',0))*2})\n")
    fr = c.post(f"{BASE}/api/projects/{pf['id']}/stages", headers=H, json={
        "type": "form", "name": "Saida", "config": {"mode": "result", "summary_key": "x"}}).json()
    c.post(f"{BASE}/api/projects/{pf['id']}/edges", headers=H,
           json={"source_stage_id": fid["id"], "target_stage_id": sc["id"]})
    c.post(f"{BASE}/api/projects/{pf['id']}/edges", headers=H,
           json={"source_stage_id": sc["id"], "target_stage_id": fr["id"]})
    c.put(f"{BASE}/api/projects/{pf['id']}/access-policy", headers=H,
          json={"access_mode": "domain", "allowed_domain": "irko.com.br"})
    c.post(f"{BASE}/api/projects/{pf['id']}/publish", headers=H)
    atok = c.post(f"{BASE}/api/app/{pf['subdomain']}/login",
                  data={"email": "ana@irko.com.br", "password": "flowdesk123"}).json()["access_token"]
    sub = c.post(f"{BASE}/api/app/{pf['subdomain']}/stages/{fid['id']}/submit",
                 data={"token": atok, "payload": json.dumps({"n": 21})}).json()
    check("submit form -> processing", sub.get("status") == "processing", f"{sub}")
    ex = poll(c, H, pf["id"], sub["execution_id"])
    check("script do fluxo executou (21*2=42)", ex["status"] == "success" and ex["output_data"].get("dobro") == 42,
          f"status={ex['status']} out={ex.get('output_data')}")

    section("Logs com filtros")
    logs = c.get(f"{BASE}/api/projects/{pid}/executions", headers=H,
                 params={"status": "error", "page_size": 50}).json()
    check("filtro de logs por status=error", logs["total"] >= 1 and all(i["status"] == "error" for i in logs["items"]))
    recent = c.get(f"{BASE}/api/projects/{pid}/executions/by-stage/recent", headers=H).json()
    check("execucoes recentes por stage", "stages" in recent and "pending" in recent)

    section("Chat (endpoints)")
    ctx = c.get(f"{BASE}/api/projects/{pid}/chat/context", headers=H).json()
    check("contexto do chat", "percent" in ctx and "ai_enabled" in ctx)
    check("pending actions lista", isinstance(
        c.get(f"{BASE}/api/projects/{pid}/pending-actions", headers=H).json(), list))

    section("WebSocket realtime")
    try:
        async def ws_test():
            import websockets
            url = f"ws://127.0.0.1:8000/ws/projects/{pid}?token={tok}"
            async with websockets.connect(url) as ws:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                return msg
        msg = asyncio.run(ws_test())
        check("ws (com token) envia 'connected'", msg.get("type") == "connected")
    except Exception as exc:
        check("ws envia 'connected'", False, str(exc)[:80])

    section("Wizard (assistente de automacao)")
    wstate = {"step": 3, "trigger": "manual", "input": {"kind": "file"},
              "process": "remover duplicados pela coluna Valor", "output": {"kind": "download"}}
    pw = c.put(f"{BASE}/api/projects/{pid}/wizard", headers=H,
               json={"state": wstate, "dirty": False}).json()
    check("wizard_state salvo e devolvido",
          pw.get("wizard_state", {}).get("process") == wstate["process"],
          f"got={pw.get('wizard_state')}")
    check("wizard_dirty inicia falso", pw.get("wizard_dirty") is False)
    got = c.get(f"{BASE}/api/projects/{pid}", headers=H).json()
    check("wizard_state persiste no GET do projeto", got.get("wizard_state", {}).get("step") == 3)
    pw2 = c.put(f"{BASE}/api/projects/{pid}/wizard", headers=H,
                json={"state": wstate, "dirty": True}).json()
    check("wizard_dirty pode ser marcado (edicao no modo avancado)", pw2.get("wizard_dirty") is True)
    nf = c.put(f"{BASE}/api/projects/999999/wizard", headers=H, json={"state": {}, "dirty": False})
    check("wizard em projeto inexistente -> 404", nf.status_code == 404, f"status={nf.status_code}")

    # montar o fluxo a partir do rascunho (modo simulado gera um script pandas)
    c.put(f"{BASE}/api/projects/{pid}/wizard", headers=H, json={"state": {
        "trigger": {"kind": "manual"}, "input": {"kind": "file"},
        "process": {"description": "remover duplicados pela coluna Valor"},
        "output": {"kind": "download"}}, "dirty": False})
    build = c.post(f"{BASE}/api/projects/{pid}/wizard/build", headers=H).json()
    check("build retorna explicacao + script .py",
          bool(build.get("explanation")) and build.get("script_file", "").endswith(".py"),
          f"got={build}")
    stids = build.get("stage_ids", {})
    check("build criou nos input/script/result",
          all(k in stids for k in ("input", "script", "result")), f"stage_ids={stids}")
    by_id = {s["id"]: s for s in c.get(f"{BASE}/api/projects/{pid}/stages", headers=H).json()}
    sfile = by_id.get(stids.get("script"), {}).get("entry_file", "")
    check("script tem entry_file .py", sfile.endswith(".py"), f"entry={sfile}")
    wfiles = c.get(f"{BASE}/api/projects/{pid}/files", headers=H).json()
    check("codigo do script foi gravado",
          any(f["path"] == sfile and len(f["content"]) > 10 for f in wfiles), f"file={sfile}")
    check("edges do grafo do wizard criados (>=2)",
          len(c.get(f"{BASE}/api/projects/{pid}/edges", headers=H).json()) >= 2)
    c.post(f"{BASE}/api/projects/{pid}/wizard/build", headers=H)
    wiz_nodes = [s for s in c.get(f"{BASE}/api/projects/{pid}/stages", headers=H).json()
                 if (s.get("config") or {}).get("_wizard_role")]
    check("rebuild idempotente (sem duplicar, <=4 nos do wizard)",
          len(wiz_nodes) <= 4, f"wiz_nodes={len(wiz_nodes)}")
    c.put(f"{BASE}/api/projects/{pid}/files", headers=H,
          json={"path": sfile, "content": "# editado manualmente no modo avancado\nx=1\n"})
    proj_after = c.get(f"{BASE}/api/projects/{pid}", headers=H).json()
    check("edicao manual (modo avancado) marca wizard_dirty=True",
          proj_after.get("wizard_dirty") is True, f"dirty={proj_after.get('wizard_dirty')}")
    pe = new_project(c, H, "QA Wizard Vazio")
    nodesc = c.post(f"{BASE}/api/projects/{pe['id']}/wizard/build", headers=H)
    check("build sem descricao -> 400", nodesc.status_code == 400, f"status={nodesc.status_code}")

    section("Limpeza")
    for ppid in CREATED_PROJECTS:
        c.delete(f"{BASE}/api/projects/{ppid}", headers=H)
    gone = all(c.get(f"{BASE}/api/projects/{ppid}", headers=H).status_code == 404 for ppid in CREATED_PROJECTS)
    check("projetos de QA removidos", gone)

    total = len(RESULTS)
    passed = sum(1 for ok, _, _ in RESULTS if ok)
    print(f"\n{'='*50}\nRESULTADO: {passed}/{total} testes passaram")
    fails = [(n, d) for ok, n, d in RESULTS if not ok]
    if fails:
        print("FALHAS:")
        for n, d in fails:
            print(f"  - {n}  [{d}]")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
