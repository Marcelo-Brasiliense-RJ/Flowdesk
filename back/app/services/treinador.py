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
