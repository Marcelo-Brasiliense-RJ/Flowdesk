"""Project settings: env vars, API keys, connectors, access control, tables."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import (
    ApiKey,
    Connector,
    DataRow,
    DataTable,
    EnvVar,
    ProjectMember,
    Role,
    User,
)
from ..schemas import (
    AccessPolicyUpdate,
    ApiKeyOut,
    ConnectorOut,
    EnvVarOut,
    EnvVarWrite,
    MemberCreate,
    MemberOut,
    ProjectOut,
    RoleCreate,
    RoleOut,
)
from .projects import get_project

router = APIRouter(prefix="/api", tags=["settings"])


# ---- env vars ----
@router.get("/projects/{project_id}/env", response_model=list[EnvVarOut])
def list_env(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_project(db, project_id, user)
    return db.query(EnvVar).filter(EnvVar.project_id == project_id).all()


@router.put("/projects/{project_id}/env", response_model=EnvVarOut)
def upsert_env(
    project_id: int, body: EnvVarWrite, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    get_project(db, project_id, user)
    ev = db.query(EnvVar).filter(EnvVar.project_id == project_id, EnvVar.key == body.key).first()
    if ev:
        ev.value, ev.secret = body.value, body.secret
    else:
        ev = EnvVar(project_id=project_id, key=body.key, value=body.value, secret=body.secret)
        db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


@router.delete("/projects/{project_id}/env/{env_id}")
def delete_env(project_id: int, env_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_project(db, project_id, user)
    db.query(EnvVar).filter(EnvVar.id == env_id, EnvVar.project_id == project_id).delete()
    db.commit()
    return {"ok": True}


# ---- api keys ----
@router.get("/projects/{project_id}/api-keys", response_model=list[ApiKeyOut])
def list_keys(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_project(db, project_id, user)
    return db.query(ApiKey).filter(ApiKey.project_id == project_id).all()


@router.post("/projects/{project_id}/api-keys", response_model=ApiKeyOut)
def create_key(project_id: int, name: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_project(db, project_id, user)
    key = ApiKey(project_id=project_id, name=name, token="fdk_" + uuid.uuid4().hex)
    db.add(key)
    db.commit()
    db.refresh(key)
    return key


@router.delete("/projects/{project_id}/api-keys/{key_id}")
def delete_key(project_id: int, key_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_project(db, project_id, user)
    db.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.project_id == project_id).delete()
    db.commit()
    return {"ok": True}


# ---- connectors ----
@router.get("/projects/{project_id}/connectors", response_model=list[ConnectorOut])
def list_connectors(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_project(db, project_id, user)
    return db.query(Connector).filter(Connector.project_id == project_id).all()


# ---- roles ----
@router.get("/projects/{project_id}/roles", response_model=list[RoleOut])
def list_roles(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_project(db, project_id, user)
    return db.query(Role).filter(Role.project_id == project_id).all()


@router.post("/projects/{project_id}/roles", response_model=RoleOut)
def create_role(
    project_id: int, body: RoleCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    get_project(db, project_id, user)
    role = Role(project_id=project_id, name=body.name, description=body.description)
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


@router.delete("/projects/{project_id}/roles/{role_id}")
def delete_role(project_id: int, role_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_project(db, project_id, user)
    db.query(Role).filter(Role.id == role_id, Role.project_id == project_id).delete()
    db.commit()
    return {"ok": True}


# ---- members (access control) ----
@router.get("/projects/{project_id}/members", response_model=list[MemberOut])
def list_members(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_project(db, project_id, user)
    return db.query(ProjectMember).filter(ProjectMember.project_id == project_id).all()


@router.post("/projects/{project_id}/members", response_model=MemberOut)
def add_member(
    project_id: int, body: MemberCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    get_project(db, project_id, user)
    existing = (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project_id, ProjectMember.email == body.email)
        .first()
    )
    if existing:
        existing.roles = body.roles
        db.commit()
        db.refresh(existing)
        return existing
    member = ProjectMember(project_id=project_id, email=body.email, roles=body.roles)
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


@router.delete("/projects/{project_id}/members/{member_id}")
def delete_member(project_id: int, member_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_project(db, project_id, user)
    db.query(ProjectMember).filter(
        ProjectMember.id == member_id, ProjectMember.project_id == project_id
    ).delete()
    db.commit()
    return {"ok": True}


@router.put("/projects/{project_id}/access-policy", response_model=ProjectOut)
def update_access_policy(
    project_id: int, body: AccessPolicyUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    project = get_project(db, project_id, user)
    if body.access_mode not in ("whitelist", "domain"):
        raise HTTPException(status_code=400, detail="Política inválida")
    project.access_mode = body.access_mode
    project.allowed_domain = body.allowed_domain
    db.commit()
    db.refresh(project)
    return project


# ---- data tables (Configurações > Tabelas) ----
@router.get("/projects/{project_id}/tables")
def list_tables(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_project(db, project_id, user)
    tables = db.query(DataTable).filter(DataTable.project_id == project_id).all()
    return [{"id": t.id, "name": t.name, "columns": t.columns} for t in tables]


@router.post("/projects/{project_id}/tables")
def create_table(
    project_id: int, name: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    get_project(db, project_id, user)
    table = DataTable(project_id=project_id, name=name, columns=[])
    db.add(table)
    db.commit()
    db.refresh(table)
    return {"id": table.id, "name": table.name, "columns": table.columns}


def _get_table(db: Session, project_id: int, table_id: int) -> DataTable:
    t = db.get(DataTable, table_id)
    if t is None or t.project_id != project_id:
        raise HTTPException(status_code=404, detail="Tabela não encontrada")
    return t


@router.patch("/projects/{project_id}/tables/{table_id}")
def update_table(
    project_id: int, table_id: int, body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    get_project(db, project_id, user)
    t = _get_table(db, project_id, table_id)
    if "name" in body:
        t.name = body["name"]
    if "columns" in body:
        t.columns = body["columns"]
    db.commit()
    db.refresh(t)
    return {"id": t.id, "name": t.name, "columns": t.columns}


@router.delete("/projects/{project_id}/tables/{table_id}")
def delete_table(project_id: int, table_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_project(db, project_id, user)
    _get_table(db, project_id, table_id)
    db.query(DataRow).filter(DataRow.table_id == table_id).delete(synchronize_session=False)
    db.query(DataTable).filter(DataTable.id == table_id).delete()
    db.commit()
    return {"ok": True}


@router.get("/projects/{project_id}/tables/{table_id}/rows")
def list_rows(project_id: int, table_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_project(db, project_id, user)
    _get_table(db, project_id, table_id)
    rows = db.query(DataRow).filter(DataRow.table_id == table_id).all()
    return [{"id": r.id, "values": r.values} for r in rows]


@router.post("/projects/{project_id}/tables/{table_id}/rows")
def add_row(
    project_id: int, table_id: int, body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    get_project(db, project_id, user)
    _get_table(db, project_id, table_id)
    row = DataRow(table_id=table_id, values=body.get("values", {}))
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "values": row.values}


@router.patch("/projects/{project_id}/tables/{table_id}/rows/{row_id}")
def update_row(
    project_id: int, table_id: int, row_id: int, body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    get_project(db, project_id, user)
    _get_table(db, project_id, table_id)
    row = db.get(DataRow, row_id)
    if row is None or row.table_id != table_id:
        raise HTTPException(status_code=404, detail="Linha não encontrada")
    row.values = body.get("values", row.values)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "values": row.values}


@router.delete("/projects/{project_id}/tables/{table_id}/rows/{row_id}")
def delete_row(project_id: int, table_id: int, row_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_project(db, project_id, user)
    _get_table(db, project_id, table_id)
    db.query(DataRow).filter(DataRow.id == row_id, DataRow.table_id == table_id).delete()
    db.commit()
    return {"ok": True}


# ---- connectors (create / update / delete) ----
@router.post("/projects/{project_id}/connectors", response_model=ConnectorOut)
def create_connector(
    project_id: int, body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    get_project(db, project_id, user)
    conn = Connector(
        project_id=project_id,
        type=body.get("type", "http"),
        name=body.get("name", "Conector"),
        config=body.get("config", {}),
        connected=bool(body.get("connected", True)),
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return conn


@router.delete("/projects/{project_id}/connectors/{connector_id}")
def delete_connector(project_id: int, connector_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_project(db, project_id, user)
    db.query(Connector).filter(Connector.id == connector_id, Connector.project_id == project_id).delete()
    db.commit()
    return {"ok": True}
