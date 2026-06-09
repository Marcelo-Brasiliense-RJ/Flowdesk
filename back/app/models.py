"""SQLAlchemy models covering the 10 FlowDesk modules.

Notes on the data model:
- Source code files (the Monaco "Codigo Fonte" explorer) live in SourceFile rows
  so edits persist in the DB.
- Runtime data files (uploads/outputs) live on disk under back/storage/<project>/
  and are browsed by the file-manager module, not stored here.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    domain: Mapped[str] = mapped_column(String(160), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    users: Mapped[list["User"]] = relationship(back_populates="organization")
    projects: Mapped[list["Project"]] = relationship(back_populates="organization")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), default="")
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    organization: Mapped[Organization] = relationship(back_populates="users")


class ProjectFolder(Base):
    __tablename__ = "project_folders"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    folder_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("project_folders.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(160))
    subdomain: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    # draft | live
    status: Mapped[str] = mapped_column(String(20), default="draft")
    output_folder_name: Mapped[str] = mapped_column(String(80), default="output")
    # whitelist | domain
    access_mode: Mapped[str] = mapped_column(String(20), default="whitelist")
    allowed_domain: Mapped[str] = mapped_column(String(160), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    organization: Mapped[Organization] = relationship(back_populates="projects")
    stages: Mapped[list["Stage"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    edges: Mapped[list["Edge"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    source_files: Mapped[list["SourceFile"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Stage(Base):
    __tablename__ = "stages"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    # form | script | job | hook | agent
    type: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(160))
    key: Mapped[str] = mapped_column(String(120))
    # form fields schema / script settings / hook config etc.
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    entry_file: Mapped[str] = mapped_column(String(255), default="")
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=120)
    pos_x: Mapped[float] = mapped_column(default=0.0)
    pos_y: Mapped[float] = mapped_column(default=0.0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    project: Mapped[Project] = relationship(back_populates="stages")

    __table_args__ = (UniqueConstraint("project_id", "key", name="uq_stage_key"),)


class Edge(Base):
    __tablename__ = "edges"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    source_stage_id: Mapped[int] = mapped_column(ForeignKey("stages.id"))
    target_stage_id: Mapped[int] = mapped_column(ForeignKey("stages.id"))
    variable_label: Mapped[str] = mapped_column(String(120), default="")

    project: Mapped[Project] = relationship(back_populates="edges")


class SourceFile(Base):
    """A file shown in the Monaco code explorer (project source code)."""

    __tablename__ = "source_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    path: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, default="")
    is_dir: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    project: Mapped[Project] = relationship(back_populates="source_files")

    __table_args__ = (UniqueConstraint("project_id", "path", name="uq_file_path"),)


class Build(Base):
    """An immutable published version (Histórico de Versões)."""

    __tablename__ = "builds"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    hash: Mapped[str] = mapped_column(String(8), index=True)
    framework_version: Mapped[str] = mapped_column(String(40), default="1.0.0")
    # live | inactive | failed
    status: Mapped[str] = mapped_column(String(20), default="inactive")
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class Execution(Base):
    __tablename__ = "executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    stage_id: Mapped[int] = mapped_column(ForeignKey("stages.id"))
    build_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("builds.id"), nullable=True
    )
    stage_name: Mapped[str] = mapped_column(String(160), default="")
    stage_type: Mapped[str] = mapped_column(String(20), default="")
    # queued | running | success | error
    status: Mapped[str] = mapped_column(String(20), default="queued")
    stdout: Mapped[str] = mapped_column(Text, default="")
    stderr: Mapped[str] = mapped_column(Text, default="")
    input_data: Mapped[dict] = mapped_column(JSON, default=dict)
    output_data: Mapped[dict] = mapped_column(JSON, default=dict)
    run_dir: Mapped[str] = mapped_column(String(255), default="")
    started_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime, nullable=True
    )


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(255), default="")


class ProjectMember(Base):
    """A user allowed into the published app + their roles (Controle de Acesso)."""

    __tablename__ = "project_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    email: Mapped[str] = mapped_column(String(200))
    roles: Mapped[list] = mapped_column(JSON, default=list)

    __table_args__ = (
        UniqueConstraint("project_id", "email", name="uq_member_email"),
    )


class EnvVar(Base):
    __tablename__ = "env_vars"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    key: Mapped[str] = mapped_column(String(120))
    value: Mapped[str] = mapped_column(Text, default="")
    secret: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (UniqueConstraint("project_id", "key", name="uq_env_key"),)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(120))
    token: Mapped[str] = mapped_column(String(80), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class Connector(Base):
    __tablename__ = "connectors"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    # google_sheets | slack | http
    type: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    connected: Mapped[bool] = mapped_column(Boolean, default=False)


class DataTable(Base):
    """Internal project database table (Configurações > Tabelas)."""

    __tablename__ = "data_tables"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(120))
    columns: Mapped[list] = mapped_column(JSON, default=list)


class DataRow(Base):
    __tablename__ = "data_rows"

    id: Mapped[int] = mapped_column(primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("data_tables.id"))
    values: Mapped[dict] = mapped_column(JSON, default=dict)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    # user | assistant
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text, default="")
    # optional structured payload (clarifying questions, etc.)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class PendingAction(Base):
    """An AI-proposed action awaiting Approve/Reject (Smart Chat)."""

    __tablename__ = "pending_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    # create_file | edit_file | install_package | create_stage
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(255))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    # pending | approved | rejected
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
