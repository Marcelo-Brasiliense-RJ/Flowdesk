"""Regressão: um script que lê arquivos (get_file) tem que ter Form de entrada.

Sem isso a automação aparece como "não recebe entrada" e o teste falha com
"arquivo de entrada não foi encontrado" (get_file retorna None). O gap: quando já
existe um stage script mas nenhum Form de entrada (ex.: script veio de um
create_stage avulso, ou o form foi removido), _ensure_runnable_workflow desistia.
"""
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Edge, Organization, Project, SourceFile, Stage
from app.routers.chat import _ensure_runnable_workflow

_CODE_2_FILES = (
    "from flowdesk_sdk import get_file, set_output, output_path\n"
    "import pandas as pd\n"
    "extrato = pd.read_excel(get_file(0))\n"
    "razao = pd.read_excel(get_file(1))\n"
    "set_output({'arquivo_resultado': str(output_path('c.xlsx')), 'resumo': {}})\n"
)


def _session():
    eng = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return Session(eng)


def test_cria_form_de_entrada_quando_script_existe_sem_entrada():
    with _session() as s:
        org = Organization(name="IRKO"); s.add(org); s.flush()
        p = Project(org_id=org.id, name="Conc", subdomain="conc"); s.add(p); s.flush()
        # script avulso, SEM Form de entrada (o estado que quebra o teste do usuário)
        s.add(Stage(project_id=p.id, type="script", name="Processamento",
                    key="proc", entry_file="conc.py", config={}))
        s.add(SourceFile(project_id=p.id, path="conc.py", content=_CODE_2_FILES))
        s.commit()

        _ensure_runnable_workflow(s, p.id, "conc.py")
        s.commit()

        forms = [st for st in s.query(Stage).filter(Stage.project_id == p.id).all()
                 if st.type == "form" and (st.config or {}).get("mode") == "input"]
        assert len(forms) == 1, "deveria ter criado o Form de entrada faltante"
        fields = forms[0].config["fields"]
        assert [f["name"] for f in fields] == ["arquivo1", "arquivo2"]
        # e o Form tem que alimentar o script existente
        edges = s.query(Edge).filter(Edge.project_id == p.id,
                                     Edge.source_stage_id == forms[0].id).all()
        assert len(edges) == 1


def test_nao_cria_entrada_para_script_que_nao_le_arquivo():
    with _session() as s:
        org = Organization(name="IRKO"); s.add(org); s.flush()
        p = Project(org_id=org.id, name="Sem arq", subdomain="semarq"); s.add(p); s.flush()
        s.add(Stage(project_id=p.id, type="script", name="Proc",
                    key="proc", entry_file="x.py", config={}))
        s.add(SourceFile(project_id=p.id, path="x.py",
                         content="from flowdesk_sdk import get_input, set_output\n"
                                 "set_output({'ok': True})\n"))
        s.commit()
        _ensure_runnable_workflow(s, p.id, "x.py")
        s.commit()
        forms = [st for st in s.query(Stage).filter(Stage.project_id == p.id).all()
                 if st.type == "form" and (st.config or {}).get("mode") == "input"]
        assert forms == [], "script sem get_file não deve ganhar upload"


def test_nao_duplica_quando_ja_ha_form_de_entrada():
    with _session() as s:
        org = Organization(name="IRKO"); s.add(org); s.flush()
        p = Project(org_id=org.id, name="Ok", subdomain="ok"); s.add(p); s.flush()
        s.add(Stage(project_id=p.id, type="form", name="Entrada", key="entrada",
                    config={"mode": "input", "fields": [{"name": "arquivo1", "type": "file"}]}))
        s.add(Stage(project_id=p.id, type="script", name="Proc",
                    key="proc", entry_file="conc.py", config={}))
        s.add(SourceFile(project_id=p.id, path="conc.py", content=_CODE_2_FILES))
        s.commit()
        _ensure_runnable_workflow(s, p.id, "conc.py")
        s.commit()
        forms = [st for st in s.query(Stage).filter(Stage.project_id == p.id).all()
                 if st.type == "form" and (st.config or {}).get("mode") == "input"]
        assert len(forms) == 1, "não deve duplicar o Form de entrada existente"
