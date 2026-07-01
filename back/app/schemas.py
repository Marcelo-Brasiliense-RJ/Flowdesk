"""Pydantic request/response schemas."""
from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, EmailStr


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- auth ----
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(ORMModel):
    id: int
    email: str
    name: str
    org_id: int
    role: str = "user"
    is_admin: bool = False
    is_dev: bool = False


# ---- gestão de usuários (Admin) ----
class AdminUserCreate(BaseModel):
    email: EmailStr
    name: str = ""
    password: str
    role: str = "user"  # admin | dev | user


class AdminUserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None  # reset de senha


class AdminUserOut(ORMModel):
    id: int
    email: str
    name: str
    role: str
    is_active: bool


# ---- projects ----
class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    folder_id: Optional[int] = None


class BulkDeleteRequest(BaseModel):
    ids: list[int]


class AutoNameIn(BaseModel):
    prompt: str = ""


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    folder_id: Optional[int] = None
    clear_folder: bool = False
    subdomain: Optional[str] = None


class WizardStateUpdate(BaseModel):
    """Salva o rascunho do assistente (wizard). `dirty` marca defasagem em relação
    ao que foi editado no modo avançado."""

    state: dict = {}
    dirty: bool = False


class WizardBuildOut(BaseModel):
    """Resultado da montagem do fluxo pelo assistente."""

    explanation: str
    script_file: str
    stage_ids: dict
    ai_enabled: bool


class WizardAnalyzeIn(BaseModel):
    """Pedido em linguagem natural para o assistente analisar e segmentar."""

    prompt: str = ""
    sample_file: Optional[str] = None


class ExplanationUpdate(BaseModel):
    """Descrição (do que a automação faz) escrita/editada pelo usuário."""

    text: str = ""


# ---- auto-reparo ----
class RepairProposeIn(BaseModel):
    execution_id: str
    hint: Optional[str] = None


class RepairProposeOut(BaseModel):
    diagnosis: str = ""
    change_summary: str = ""
    fixed_code: str = ""
    has_changes: bool = False


class RepairApplyIn(BaseModel):
    code: str


class ReportSeedIn(BaseModel):
    execution_id: str


class ReportRepairIn(BaseModel):
    execution_id: str
    message: str


class ProjectOut(ORMModel):
    id: int
    name: str
    subdomain: str
    description: str
    status: str
    folder_id: Optional[int]
    output_folder_name: str
    access_mode: str
    allowed_domain: str
    wizard_state: dict = {}
    wizard_dirty: bool = False
    phase: str = ""
    plan: dict = {}
    accounting_profile: dict = {}
    created_at: dt.datetime
    updated_at: dt.datetime
    owner_name: Optional[str] = None
    execution_count: int = 0


class FolderCreate(BaseModel):
    name: str


class FolderOut(ORMModel):
    id: int
    name: str


# ---- stages / edges ----
class StageCreate(BaseModel):
    type: str
    name: str
    key: Optional[str] = None
    config: dict = {}
    pos_x: float = 0.0
    pos_y: float = 0.0
    timeout_seconds: int = 120


class StageUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[dict] = None
    pos_x: Optional[float] = None
    pos_y: Optional[float] = None
    timeout_seconds: Optional[int] = None


class StageOut(ORMModel):
    id: int
    type: str
    name: str
    key: str
    config: dict
    entry_file: str
    timeout_seconds: int
    pos_x: float
    pos_y: float


class EdgeCreate(BaseModel):
    source_stage_id: int
    target_stage_id: int
    variable_label: str = ""


class EdgeOut(ORMModel):
    id: int
    source_stage_id: int
    target_stage_id: int
    variable_label: str


# ---- source files ----
class SourceFileOut(ORMModel):
    id: int
    path: str
    content: str
    is_dir: bool


class SourceFileWrite(BaseModel):
    path: str
    content: str = ""
    is_dir: bool = False


# ---- executions ----
class ExecutionOut(ORMModel):
    id: str
    project_id: int
    stage_id: int
    build_id: Optional[int]
    stage_name: str
    stage_type: str
    status: str
    stdout: str
    stderr: str
    input_data: dict
    output_data: dict
    started_at: dt.datetime
    finished_at: Optional[dt.datetime]


# ---- builds ----
class BuildOut(ORMModel):
    id: int
    hash: str
    framework_version: str
    status: str
    created_at: dt.datetime


# ---- access control ----
class RoleCreate(BaseModel):
    name: str
    description: str = ""


class RoleOut(ORMModel):
    id: int
    name: str
    description: str


class MemberCreate(BaseModel):
    email: EmailStr
    roles: list[str] = []


class MemberOut(ORMModel):
    id: int
    email: str
    roles: list


class AccessPolicyUpdate(BaseModel):
    access_mode: str
    allowed_domain: str = ""


# ---- env vars / api keys / connectors ----
class EnvVarWrite(BaseModel):
    key: str
    value: str = ""
    secret: bool = True


class EnvVarOut(ORMModel):
    id: int
    key: str
    value: str
    secret: bool


class ApiKeyOut(ORMModel):
    id: int
    name: str
    token: str
    created_at: dt.datetime


class ConnectorOut(ORMModel):
    id: int
    type: str
    name: str
    connected: bool
    config: dict


# ---- chat ----
class ChatSendRequest(BaseModel):
    content: str
    attachments: list[str] = []


class ChatMessageOut(ORMModel):
    id: int
    role: str
    content: str
    meta: dict
    tokens: int
    created_at: dt.datetime


class PendingActionOut(ORMModel):
    id: int
    kind: str
    title: str
    payload: dict
    status: str
    created_at: dt.datetime


# ---- published app ----
class PublishedAppInfo(BaseModel):
    project: ProjectOut
    stages: list[StageOut]
    edges: list[EdgeOut]
    entry_stage_id: Optional[int]


class FormSubmit(BaseModel):
    values: dict[str, Any] = {}


TokenResponse.model_rebuild()
