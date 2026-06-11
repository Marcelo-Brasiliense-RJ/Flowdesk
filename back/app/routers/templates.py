"""Galeria de modelos prontos: automações típicas da IRKO instanciáveis em 1 clique.

Cada modelo define o fluxo completo (Form de entrada -> Script -> Form de resultado)
com código testável. Instanciar cria um projeto normal, que abre no Assistente já
pronto para testar.
"""
from __future__ import annotations

import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Edge, Project, SourceFile, Stage, User
from ..services import storage
from .projects import slugify

router = APIRouter(prefix="/api", tags=["templates"])


_TOTAIS_VENDAS = '''"""Totais de uma planilha: total geral e total por categoria."""
import pandas as pd
from flowdesk_sdk import get_file, set_output, output_path

df = pd.read_excel(get_file())
col_num = df.select_dtypes("number").columns
if len(col_num) == 0:
    set_output({"erro": "A planilha não tem coluna numérica para somar."})
else:
    valor = col_num[-1]
    col_txt = [c for c in df.columns if c != valor]
    grupo = col_txt[0] if col_txt else None
    total = float(df[valor].sum())
    out = output_path("totais.xlsx")
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        pd.DataFrame({grupo or "grupo": ["Total Geral"], valor: [total]}).to_excel(
            w, sheet_name="Resumo", index=False)
        if grupo:
            df.groupby(grupo)[valor].sum().reset_index().to_excel(
                w, sheet_name="Por grupo", index=False)
    resumo = {"total_geral": total, "linhas": len(df)}
    if grupo:
        resumo["grupos"] = int(df[grupo].nunique())
    set_output({"arquivo_resultado": str(out), "resumo": resumo})
'''

_CONCILIACAO = '''"""Concilia duas planilhas por uma chave comum e aponta divergências."""
import pandas as pd
from flowdesk_sdk import get_file, set_output, output_path

df_a = pd.read_excel(get_file(0))
df_b = pd.read_excel(get_file(1))
comuns = [c for c in df_a.columns if c in df_b.columns]
chave = comuns[0] if comuns else df_a.columns[0]
a_keys = set(df_a[chave].astype(str))
b_keys = set(df_b[chave].astype(str))
out = output_path("conciliacao.xlsx")
with pd.ExcelWriter(out, engine="openpyxl") as w:
    df_a[df_a[chave].astype(str).isin(a_keys & b_keys)].to_excel(w, sheet_name="Conciliados", index=False)
    df_a[df_a[chave].astype(str).isin(a_keys - b_keys)].to_excel(w, sheet_name="So_na_A", index=False)
    df_b[df_b[chave].astype(str).isin(b_keys - a_keys)].to_excel(w, sheet_name="So_na_B", index=False)
set_output({
    "arquivo_resultado": str(out),
    "resumo": {"chave": str(chave), "conciliados": len(a_keys & b_keys),
               "so_na_a": len(a_keys - b_keys), "so_na_b": len(b_keys - a_keys)},
})
'''

_PDF_PARA_PLANILHA = '''"""Extrai o texto de um PDF (editável ou escaneado) para uma planilha."""
import pandas as pd
from flowdesk_sdk import get_file, set_output, output_path, extract_document

doc = extract_document(get_file())
linhas = [l["text"] for l in doc["lines"]]
out = output_path("texto_extraido.xlsx")
pd.DataFrame({"linha": range(1, len(linhas) + 1), "texto": linhas}).to_excel(out, index=False)
set_output({
    "arquivo_resultado": str(out),
    "resumo": {"linhas_extraidas": len(linhas), "fonte": doc["source"],
               "confianca_media": doc["mean_confidence"]},
    "_ocr_review": {"text": doc["text"], "mean_confidence": doc["mean_confidence"],
                    "needs_review": doc["needs_review"],
                    "low_confidence": [l["text"] for l in doc["low_confidence"]]},
})
'''

TEMPLATES: dict[str, dict] = {
    "totais-planilha": {
        "name": "Totais de uma planilha",
        "description": "Soma o total geral e o total por grupo (ex: vendas por produto) e gera um Excel.",
        "input_fields": [{"name": "arquivo", "label": "Planilha (.xlsx)", "type": "file"}],
        "code": _TOTAIS_VENDAS,
    },
    "conciliacao-planilhas": {
        "name": "Conciliação de duas planilhas",
        "description": "Compara duas planilhas por uma chave comum e separa conciliados e divergências.",
        "input_fields": [
            {"name": "planilha_a", "label": "Planilha A", "type": "file"},
            {"name": "planilha_b", "label": "Planilha B", "type": "file"},
        ],
        "code": _CONCILIACAO,
    },
    "pdf-para-planilha": {
        "name": "PDF para planilha (com OCR)",
        "description": "Lê um PDF (mesmo escaneado) com OCR local e entrega o texto estruturado em Excel, com revisão de confiança.",
        "input_fields": [{"name": "arquivo", "label": "PDF ou imagem", "type": "file"}],
        "code": _PDF_PARA_PLANILHA,
    },
}


@router.get("/templates")
def list_templates(user: User = Depends(get_current_user)):
    return [
        {"key": k, "name": t["name"], "description": t["description"]}
        for k, t in TEMPLATES.items()
    ]


@router.post("/templates/{key}/instantiate")
def instantiate_template(
    key: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tpl = TEMPLATES.get(key)
    if tpl is None:
        raise HTTPException(status_code=404, detail="Modelo não encontrado")

    base = slugify(tpl["name"])
    sub = base
    while db.query(Project).filter(Project.subdomain == sub).first():
        sub = f"{base}-{_uuid.uuid4().hex[:4]}"
    project = Project(
        org_id=user.org_id, name=tpl["name"], subdomain=sub,
        description=tpl["description"], status="draft",
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    storage.ensure_project_dirs(project)

    form_in = Stage(
        project_id=project.id, type="form", name="Entrada", key="entrada",
        config={"title": tpl["name"], "mode": "input", "submit_label": "Executar",
                "fields": tpl["input_fields"]},
        pos_x=40, pos_y=120,
    )
    script = Stage(
        project_id=project.id, type="script", name="Processamento", key="processamento",
        entry_file="processar.py", config={}, pos_x=360, pos_y=120,
    )
    form_out = Stage(
        project_id=project.id, type="form", name="Resultado", key="resultado",
        config={"title": "Resultado", "mode": "result",
                "summary_key": "resumo", "result_file_key": "arquivo_resultado"},
        pos_x=680, pos_y=120,
    )
    db.add_all([form_in, script, form_out])
    db.flush()
    db.add_all([
        Edge(project_id=project.id, source_stage_id=form_in.id,
             target_stage_id=script.id, variable_label="entrada"),
        Edge(project_id=project.id, source_stage_id=script.id,
             target_stage_id=form_out.id, variable_label="resultado"),
    ])
    db.add_all([
        SourceFile(project_id=project.id, path="processar.py", content=tpl["code"]),
        SourceFile(project_id=project.id, path="requirements.txt", content="pandas\nopenpyxl\n"),
        SourceFile(project_id=project.id, path="README.md",
                   content=f"# {tpl['name']}\n\n{tpl['description']}\n"),
    ])
    # marca o rascunho do assistente como montado para abrir direto na revisão
    project.wizard_state = {
        "_built": True,
        "trigger": {"kind": "manual"},
        "input": {"kind": "file"},
        "process": {"description": tpl["description"]},
        "output": {"kind": "download"},
    }
    db.commit()
    return {"project_id": project.id, "name": project.name}
