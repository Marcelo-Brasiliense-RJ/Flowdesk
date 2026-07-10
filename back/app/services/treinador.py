"""Treinador: agente de auto-evolução (fora do caminho crítico).

Colhe automações publicadas e validadas, guarda plano anonimizado + código como
exemplos few-shot, registra eventos de reparo, e destila propostas de melhoria de
prompt para os agentes de build. Persiste em JSON no STORAGE_DIR, espelhando
services/ai_config.py (zero migração). NADA aqui roda no caminho crítico de
execução/publish: é chamado por hooks best-effort e por endpoints de admin.
"""
from __future__ import annotations

import hashlib
import json
import threading

from ..config import STORAGE_DIR
from ..database import SessionLocal

_DIR = STORAGE_DIR / "treinador"
_lock = threading.Lock()

# arquivos do store
def _examples_path():
    return _DIR / "examples.json"

def _proposals_path():
    return _DIR / "proposals.json"

def _repairs_path():
    return _DIR / "repairs.json"

def _meta_path():
    return _DIR / "meta.json"


def _load(path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(path, data: dict) -> None:
    with _lock:
        _DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _examples() -> list[dict]:
    return _load(_examples_path()).get("items", [])


def _proposals() -> list[dict]:
    return _load(_proposals_path()).get("items", [])


def _repairs() -> list[dict]:
    return _load(_repairs_path()).get("items", [])


def is_validated(db, project_id: int) -> bool:
    """Publicada E estável: status live, e entre as últimas 5 execuções há pelo menos
    um sucesso e nenhum erro. É o sinal de 'boa o suficiente para virar exemplo'."""
    from ..models import Execution, Project

    project = db.get(Project, project_id)
    if project is None or project.status != "live":
        return False
    recent = (
        db.query(Execution)
        .filter(Execution.project_id == project_id)
        .order_by(Execution.started_at.desc())
        .limit(5)
        .all()
    )
    statuses = [e.status for e in recent]
    return ("success" in statuses) and ("error" not in statuses)


def _source_fingerprint(db, project_id: int) -> str:
    """sha1 do código atual do projeto. Muda quando o código muda -> re-colhe uma
    versão validada nova; igual -> dedup (não re-anonimiza a cada execução)."""
    from ..models import SourceFile

    files = (
        db.query(SourceFile)
        .filter(SourceFile.project_id == project_id)
        .order_by(SourceFile.path)
        .all()
    )
    blob = "\n".join(f"{f.path}\x00{f.content or ''}" for f in files if not f.is_dir)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def _tokens(s: str) -> set:
    return {w for w in (s or "").lower().split() if len(w) > 3}


def _score(plan: dict, ex_plan: dict) -> int:
    score = 0
    if bool(plan.get("contabil")) == bool(ex_plan.get("contabil")) and plan.get("contabil"):
        score += 2
    if (plan.get("fonte") or {}).get("formato") and \
       (plan.get("fonte") or {}).get("formato") == (ex_plan.get("fonte") or {}).get("formato"):
        score += 2
    if (plan.get("saida") or {}).get("formato") and \
       (plan.get("saida") or {}).get("formato") == (ex_plan.get("saida") or {}).get("formato"):
        score += 1
    overlap = _tokens(plan.get("regra_negocio", "")) & _tokens(ex_plan.get("regra_negocio", ""))
    score += len(overlap)
    return score


def select_examples(plan: dict, k: int = 2) -> list[dict]:
    """Exemplos validados mais parecidos com o plano atual (heurística sobre o plano).
    Só retorna quem tem score >= 1 (evita injetar exemplo irrelevante)."""
    scored = [(_score(plan or {}, ex.get("plan") or {}), ex) for ex in _examples()]
    scored = [(s, ex) for s, ex in scored if s >= 1]
    scored.sort(key=lambda t: t[0], reverse=True)
    return [ex for _, ex in scored[:k]]


def examples_context(plan: dict) -> str:
    """Bloco de sistema com exemplos validados, para o Construtor/Planejador se
    espelharem no que já deu certo. Vazio quando não há exemplo relevante."""
    picked = select_examples(plan, k=2)
    if not picked:
        return ""
    blocks = []
    for i, ex in enumerate(picked, 1):
        blocks.append(
            f"EXEMPLO {i} (automação já publicada e validada em produção):\n"
            "PLANO:\n" + json.dumps(ex.get("plan") or {}, ensure_ascii=False, indent=2)
            + "\nCÓDIGO:\n" + (ex.get("code") or "")[:3000]
        )
    return (
        "EXEMPLOS DE REFERÊNCIA (automações que foram ao ar e rodaram sem erro). "
        "Use-os como guia de estrutura e estilo; NÃO copie dados, apenas o padrão:\n\n"
        + "\n\n".join(blocks)
    )


TREINADOR_PROMPT = (
    "Você é o Treinador do FlowDesk. Seu trabalho é analisar automações que foram "
    "publicadas e validadas (rodaram em produção sem erro) e os ajustes feitos até "
    "elas irem ao ar, para melhorar os agentes que constroem automações. Você tem "
    "duas tarefas, indicadas em cada chamada:\n"
    "1) ANONIMIZAR: dado um PLANO de automação, remova ou generalize qualquer dado "
    "que identifique um cliente/empresa específico (razões sociais, nomes próprios, "
    "CNPJ, nomes de contas específicas, nomes de colunas com identificadores), "
    "mantendo intacto o PADRÃO estrutural (formatos, tipos de regra, tipo de saída). "
    "Responda SOMENTE o JSON do plano anonimizado.\n"
    "2) DESTILAR: dado um conjunto de exemplos validados e ajustes (reparos, "
    "rejeições), e o system prompt ATUAL de um agente, proponha um system prompt "
    "MELHOR que evite os erros observados e reforce os padrões que deram certo. "
    "Não invente regras não sustentadas pelos exemplos. Responda SOMENTE em JSON "
    '{"proposed_prompt": "...", "rationale": "1 a 3 frases do que muda e por quê"}.'
)


def anonymize_plan(plan: dict) -> dict | None:
    """Anonimiza o plano via agente Treinador. Retorna None se a IA falhar ou
    devolver algo inválido (nesse caso NÃO se grava exemplo, nunca vaza dado cru)."""
    from ..config import settings
    if not settings.ai_enabled:
        return None
    from ..routers.orchestrator import call_agent

    raw = call_agent(
        "treinador", TREINADOR_PROMPT,
        [{"role": "user", "content": "TAREFA: ANONIMIZAR\nPLANO:\n"
          + json.dumps(plan or {}, ensure_ascii=False)}],
        json_mode=True,
    )
    try:
        data = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return None
    # o modelo pode devolver o plano direto ou aninhado em "plan"
    result = data.get("plan") if isinstance(data.get("plan"), dict) else data
    return result if isinstance(result, dict) and result else None


def _entry_code(db, project_id: int) -> str:
    """Conteúdo do maior .py do projeto (o script principal da automação)."""
    from ..models import SourceFile

    pys = [
        f for f in db.query(SourceFile).filter(SourceFile.project_id == project_id).all()
        if f.path.endswith(".py") and not f.is_dir and (f.content or "").strip()
    ]
    if not pys:
        return ""
    return max(pys, key=lambda f: len(f.content or "")).content


def harvest_project(project_id: int) -> bool:
    """Best-effort: se o projeto está validado e ainda não foi colhido nesta versão
    de código, anonimiza o plano e grava um exemplo. NUNCA lança (é chamado por hook
    fora do caminho crítico). Retorna True se gravou um exemplo novo."""
    try:
        db = SessionLocal()
    except Exception:
        return False
    try:
        if not is_validated(db, project_id):
            return False
        from ..models import Project

        project = db.get(Project, project_id)
        fp = _source_fingerprint(db, project_id)
        if any(ex.get("fingerprint") == fp for ex in _examples()):
            return False  # dedup: mesma versão já colhida
        code = _entry_code(db, project_id)
        if not code:
            return False
        anon = anonymize_plan((project.plan if project else {}) or {})
        if anon is None:
            return False  # anonimização falhou -> não grava (confidencialidade)
        data = _load(_examples_path())
        items = data.get("items", [])
        items.append({"plan": anon, "code": code, "fingerprint": fp, "project_id": project_id})
        _save(_examples_path(), {"items": items})
        # sinaliza que há exemplos novos e destila propostas ao atingir o limiar
        _bump_new_examples()
        maybe_distill()
        return True
    except Exception:
        return False
    finally:
        try:
            db.close()
        except Exception:
            pass


def _bump_new_examples() -> None:
    """Contador de exemplos novos desde a última destilação (limiar da Task 8)."""
    meta = _load(_meta_path())
    meta["new_examples"] = int(meta.get("new_examples", 0)) + 1
    _save(_meta_path(), meta)


def record_repair(project_id: int, symptom: str, root_cause: str, fix: str,
                  source: str = "manual") -> bool:
    """Registra um evento de reparo (sintoma -> causa-raiz -> correção) no store do
    Treinador. Sinal de treino do lado das FALHAS (complementa os exemplos de sucesso
    do harvest). Best-effort, sem DB, dedup por fingerprint; NUNCA lança. Retorna True
    se gravou um evento novo. NÃO guarda dados de execução nem arquivos enviados."""
    try:
        fp = hashlib.sha1(
            f"{project_id}|{symptom}|{fix}".encode("utf-8")
        ).hexdigest()[:16]
        data = _load(_repairs_path())
        items = data.get("items", [])
        if any(r.get("fingerprint") == fp for r in items):
            return False  # dedup: mesmo reparo já registrado
        items.append({"project_id": project_id, "symptom": symptom,
                      "root_cause": root_cause, "fix": fix, "source": source,
                      "fingerprint": fp})
        _save(_repairs_path(), {"items": items})
        return True
    except Exception:
        return False


# ---- Destilação por limiar + propostas de prompt (aprovação humana) ----

DISTILL_THRESHOLD = 10  # exemplos novos até propor uma melhoria de prompt
_BUILD_AGENTS = ["planejador", "construtor", "nomeador"]


def new_examples_count() -> int:
    return int(_load(_meta_path()).get("new_examples", 0))


def maybe_distill(agent_ids=None) -> None:
    """Best-effort: quando acumula exemplos novos suficientes, destila propostas e
    zera o contador. Chamado pelo hook de colheita, fora do caminho crítico."""
    try:
        if new_examples_count() < DISTILL_THRESHOLD:
            return
        distill(agent_ids or _BUILD_AGENTS)
        meta = _load(_meta_path())
        meta["new_examples"] = 0
        _save(_meta_path(), meta)
    except Exception:
        pass


def _proposal_id(agent_id: str, proposed_prompt: str) -> str:
    return hashlib.sha1(f"{agent_id}|{proposed_prompt}".encode("utf-8")).hexdigest()[:12]


def _distill_agent(agent_id: str, exemplos: list[dict], repairs: list[dict]) -> dict | None:
    """Chama o Treinador em modo DESTILAR: propõe um prompt melhor para o agente a
    partir dos exemplos validados e dos reparos. None se a IA falhar."""
    from ..config import settings
    if not settings.ai_enabled:
        return None
    from ..routers.orchestrator import call_agent  # treinador.py está em services/
    from . import ai_config

    atual = ai_config.get_prompt(agent_id) or ""
    ex_txt = "\n\n".join(
        json.dumps(e.get("plan") or {}, ensure_ascii=False) + "\n" + (e.get("code") or "")[:1500]
        for e in exemplos[:5]
    )
    rep_txt = "\n".join(f"- {r.get('symptom', '')} -> {r.get('fix', '')}" for r in repairs[:10])
    raw = call_agent(
        "treinador", TREINADOR_PROMPT,
        [{"role": "user", "content":
          f"TAREFA: DESTILAR\nAGENTE: {agent_id}\nPROMPT ATUAL:\n{atual}\n\n"
          f"EXEMPLOS VALIDADOS:\n{ex_txt}\n\nREPAROS OBSERVADOS:\n{rep_txt}"}],
        json_mode=True,
    )
    try:
        d = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return None
    return d if isinstance(d, dict) and d.get("proposed_prompt") else None


def distill(agent_ids=None) -> None:
    """Gera uma proposta de prompt (status pending) por agente. Best-effort."""
    exemplos, repairs = _examples(), _repairs()
    data = _load(_proposals_path())
    items = data.get("items", [])
    existing = {p.get("id") for p in items}
    for agent_id in (agent_ids or _BUILD_AGENTS):
        try:
            prop = _distill_agent(agent_id, exemplos, repairs)
        except Exception:
            prop = None
        if not prop or not prop.get("proposed_prompt"):
            continue
        pid = _proposal_id(agent_id, prop["proposed_prompt"])
        if pid in existing:
            continue
        items.append({"id": pid, "agent_id": agent_id,
                      "proposed_prompt": prop["proposed_prompt"],
                      "rationale": prop.get("rationale", ""), "status": "pending"})
        existing.add(pid)
    _save(_proposals_path(), {"items": items})


def list_proposals(status: str | None = None) -> list[dict]:
    return [p for p in _proposals() if status is None or p.get("status") == status]


def resolve_proposal(proposal_id: str, approved: bool) -> bool:
    """Aprova (aplica o prompt na fonte que get_prompt lê) ou rejeita. Retorna
    False se não achar a proposta ou se a aplicação falhar."""
    data = _load(_proposals_path())
    items = data.get("items", [])
    for p in items:
        if p.get("id") != proposal_id:
            continue
        if approved:
            try:
                from . import ai_config
                ai_config.apply_prompt(p["agent_id"], p["proposed_prompt"])
            except Exception:
                return False
            p["status"] = "approved"
        else:
            p["status"] = "rejected"
        _save(_proposals_path(), {"items": items})
        return True
    return False
