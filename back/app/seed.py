"""Seed data: 1 organization, 3 users, 2 projects.

The "Conciliador de Planilhas" project ships a working 3-node workflow:
    Form (upload) -> Script (pandas reconciliation) -> Form (download)
and is published so its app is immediately reachable at /app/conciliador.
"""
from __future__ import annotations

import uuid

from .auth import hash_password
from .database import SessionLocal
from .models import (
    Build,
    Edge,
    EnvVar,
    Organization,
    Project,
    ProjectFolder,
    ProjectMember,
    Role,
    SourceFile,
    Stage,
    User,
)
from .services import storage

RECONCILE_SCRIPT = '''"""Conciliação de duas planilhas (.xlsx) por uma chave comum."""
import pandas as pd
from flowdesk_sdk import get_input, set_output, output_path, log


def main():
    data = get_input()
    a_path = data.get("planilha_a") or data.get("arquivo")
    b_path = data.get("planilha_b")
    log("Planilha A:", a_path)
    log("Planilha B:", b_path)

    if not a_path:
        set_output({"erro": "Nenhuma planilha enviada."})
        return

    df_a = pd.read_excel(a_path)
    if b_path:
        df_b = pd.read_excel(b_path)
    else:
        xls = pd.ExcelFile(a_path)
        if len(xls.sheet_names) >= 2:
            df_a = pd.read_excel(a_path, sheet_name=xls.sheet_names[0])
            df_b = pd.read_excel(a_path, sheet_name=xls.sheet_names[1])
        else:
            df_b = df_a.iloc[0:0]

    common = [c for c in df_a.columns if c in df_b.columns]
    key = common[0] if common else df_a.columns[0]
    log("Conciliando pela chave:", key)

    a_keys = set(df_a[key].astype(str)) if key in df_a.columns else set()
    b_keys = set(df_b[key].astype(str)) if key in df_b.columns else set()

    conciliados = a_keys & b_keys
    so_a = a_keys - b_keys
    so_b = b_keys - a_keys

    # divergencias: mesma chave nas duas planilhas, porem com VALOR (numerico) diferente
    value_cols = [
        c for c in df_a.columns
        if c in df_b.columns and c != key and pd.api.types.is_numeric_dtype(df_a[c])
    ]
    a_by = {str(k): row for k, row in df_a.set_index(key).iterrows()}
    b_by = {str(k): row for k, row in df_b.set_index(key).iterrows()}
    div_rows = []
    for k in sorted(conciliados):
        ra, rb = a_by.get(k), b_by.get(k)
        if ra is None or rb is None:
            continue
        diff = {c: (ra[c], rb[c]) for c in value_cols if ra[c] != rb[c]}
        if diff:
            row = {key: k}
            for c, (va, vb) in diff.items():
                row[c + "_A"], row[c + "_B"] = va, vb
            div_rows.append(row)
    df_div = pd.DataFrame(div_rows)

    out = output_path("conciliacao_resultado.xlsx")
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df_a[df_a[key].astype(str).isin(conciliados)].to_excel(
            writer, sheet_name="Conciliados", index=False)
        df_a[df_a[key].astype(str).isin(so_a)].to_excel(
            writer, sheet_name="Somente_A", index=False)
        df_b[df_b[key].astype(str).isin(so_b)].to_excel(
            writer, sheet_name="Somente_B", index=False)
        if not df_div.empty:
            df_div.to_excel(writer, sheet_name="Divergencias", index=False)

    resumo = {
        "chave": str(key),
        "conciliados": len(conciliados),
        "somente_a": len(so_a),
        "somente_b": len(so_b),
        "divergencias": len(div_rows),
        "total_a": len(a_keys),
        "total_b": len(b_keys),
    }
    log("Resumo:", resumo)
    set_output({"arquivo_resultado": str(out), "resumo": resumo})


if __name__ == "__main__":
    main()
'''

UPLOAD_FORM_STUB = '''"""Form: Upload de planilhas (renderizado a partir do schema)."""
# Este arquivo é um stub legível. O FlowDesk renderiza o formulário a partir
# do schema declarativo do nó (config.fields).
FORM = {
    "title": "Conciliação de Planilhas",
    "fields": [
        {"name": "planilha_a", "label": "Planilha A (sistema)", "type": "file"},
        {"name": "planilha_b", "label": "Planilha B (banco)", "type": "file"},
    ],
}
'''

DOWNLOAD_FORM_STUB = '''"""Form: Resultado / download (renderizado a partir do schema)."""
FORM = {
    "title": "Resultado da Conciliação",
    "mode": "result",
    "result_file_key": "arquivo_resultado",
    "summary_key": "resumo",
}
'''


def seed_if_empty() -> None:
    db = SessionLocal()
    try:
        if db.query(Organization).first():
            return

        org = Organization(name="IRKO", domain="irko.com.br")
        db.add(org)
        db.flush()

        pwd = hash_password("REMOVED-SEED-PASSWORD")
        db.add_all(
            [
                User(org_id=org.id, email="admin@irko.com.br", name="Admin IRKO",
                     hashed_password=pwd),
                User(org_id=org.id, email="ana@irko.com.br", name="Ana Souza",
                     hashed_password=pwd),
                User(org_id=org.id, email="bruno@irko.com.br", name="Bruno Lima",
                     hashed_password=pwd),
            ]
        )

        folder = ProjectFolder(org_id=org.id, name="Operações")
        db.add(folder)
        db.flush()

        # ---- Project 1: Conciliador de Planilhas (published) ----
        proj = Project(
            org_id=org.id,
            folder_id=folder.id,
            name="Conciliador de Planilhas",
            subdomain="conciliador",
            description="Concilia duas planilhas e gera um relatório de divergências.",
            status="live",
            output_folder_name="resultados",
            access_mode="domain",
            allowed_domain="irko.com.br",
        )
        db.add(proj)
        db.flush()
        storage.ensure_project_dirs(proj)

        form_in = Stage(
            project_id=proj.id, type="form", name="Upload das Planilhas",
            key="upload", pos_x=40, pos_y=120,
            config={
                "title": "Conciliação de Planilhas",
                "description": "Envie as duas planilhas (.xlsx) que deseja conciliar.",
                "submit_label": "Conciliar",
                "mode": "input",
                "fields": [
                    {"name": "planilha_a", "label": "Planilha A (sistema)", "type": "file"},
                    {"name": "planilha_b", "label": "Planilha B (banco)", "type": "file"},
                ],
            },
        )
        script = Stage(
            project_id=proj.id, type="script", name="Processar Conciliação",
            key="processar", entry_file="processar.py", timeout_seconds=120,
            pos_x=360, pos_y=120, config={"description": "Conciliação com pandas"},
        )
        form_out = Stage(
            project_id=proj.id, type="form", name="Download do Resultado",
            key="resultado", pos_x=680, pos_y=120,
            config={
                "title": "Resultado da Conciliação",
                "description": "Sua conciliação foi processada com sucesso.",
                "mode": "result",
                "result_file_key": "arquivo_resultado",
                "summary_key": "resumo",
            },
        )
        db.add_all([form_in, script, form_out])
        db.flush()

        db.add_all(
            [
                Edge(project_id=proj.id, source_stage_id=form_in.id,
                     target_stage_id=script.id, variable_label="planilhas"),
                Edge(project_id=proj.id, source_stage_id=script.id,
                     target_stage_id=form_out.id, variable_label="resultado"),
            ]
        )

        db.add_all(
            [
                SourceFile(project_id=proj.id, path="processar.py", content=RECONCILE_SCRIPT),
                SourceFile(project_id=proj.id, path="upload.py", content=UPLOAD_FORM_STUB),
                SourceFile(project_id=proj.id, path="resultado.py", content=DOWNLOAD_FORM_STUB),
                SourceFile(project_id=proj.id, path="requirements.txt",
                           content="pandas\nopenpyxl\n"),
                SourceFile(project_id=proj.id, path="README.md",
                           content="# Conciliador de Planilhas\n\n"
                                   "Form de upload -> Script pandas -> Form de download.\n"),
            ]
        )

        db.add_all(
            [
                Role(project_id=proj.id, name="User",
                     description="Acesso de execução às aplicações publicadas."),
                Role(project_id=proj.id, name="Dev",
                     description="Acesso de edição e configuração do projeto."),
            ]
        )
        db.add_all(
            [
                ProjectMember(project_id=proj.id, email="admin@irko.com.br", roles=["Dev"]),
                ProjectMember(project_id=proj.id, email="ana@irko.com.br", roles=["Dev"]),
                ProjectMember(project_id=proj.id, email="bruno@irko.com.br", roles=["User"]),
            ]
        )
        db.add(EnvVar(project_id=proj.id, key="AMBIENTE", value="producao", secret=False))

        # publish an initial live build
        db.add(
            Build(
                project_id=proj.id, hash=uuid.uuid4().hex[:8],
                framework_version="1.0.0", status="live",
                snapshot={"note": "build inicial do seed"},
            )
        )

        # materialize the source so the script can run immediately
        storage.materialize_sources(db, proj)

        # ---- Project 2: Relatório de Despesas (draft) ----
        proj2 = Project(
            org_id=org.id,
            folder_id=folder.id,
            name="Relatório de Despesas",
            subdomain="despesas",
            description="Consolida notas e gera relatório mensal de despesas.",
            status="draft",
            output_folder_name="output",
        )
        db.add(proj2)
        db.flush()
        storage.ensure_project_dirs(proj2)
        db.add_all(
            [
                Stage(project_id=proj2.id, type="form", name="Entrada de Notas",
                      key="entrada", pos_x=40, pos_y=120,
                      config={"title": "Notas", "mode": "input", "fields": []}),
                Role(project_id=proj2.id, name="User", description="Execução."),
                Role(project_id=proj2.id, name="Dev", description="Edição."),
                SourceFile(project_id=proj2.id, path="requirements.txt", content="\n"),
            ]
        )

        db.commit()
    finally:
        db.close()
