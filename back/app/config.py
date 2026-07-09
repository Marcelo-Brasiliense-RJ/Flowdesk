"""Application configuration loaded from environment / .env."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACK_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BACK_DIR / "storage"
DB_PATH = BACK_DIR / "flowdesk.db"
# Código materializado para execução (script do projeto + flowdesk_sdk.py). Fica
# FORA de BACK_DIR de propósito: o runtime regrava esses .py a cada execução e, se
# ficassem sob back/, o `uvicorn --reload` (que observa o diretório de trabalho)
# reiniciaria o servidor no meio da execução e mataria o teste. Os dados do projeto
# (uploads, output, runs) continuam em STORAGE_DIR; só o código roda a partir daqui.
RUNTIME_SRC_DIR = Path(tempfile.gettempdir()) / "flowdesk-runtime-src"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACK_DIR / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    secret_key: str = "flowdesk-dev-secret"
    access_token_expire_minutes: int = 60 * 24 * 7
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_model_codegen: str = "gpt-5.3-codex"
    openai_model_strong: str = "gpt-4.1"
    script_python: str = ""
    # Backend de execução de scripts: "local" (subprocesso na máquina, default)
    # ou "docker" (contêiner Linux efêmero isolado, ver S1 parte 2).
    execution_backend: str = "local"
    frontend_origin: str = "http://localhost:5173"
    # Conexão Postgres (Supabase). Vazio = usa SQLite local (flowdesk.db).
    supabase_db_url: str = ""
    database_url: str = ""
    # Quando true, o app PUBLICADO (/app/<sub>) fica aberto, SEM login.
    # Temporário/dev: deixa qualquer pessoa com o link executar. Desligue para
    # restaurar o controle de acesso (whitelist/domínio).
    public_apps_open: bool = False
    # E-mails com privilégio de admin (ex.: exclusão em massa de projetos).
    # Lista separada por vírgula via env ADMIN_EMAILS.
    admin_emails: str = "admin@irko.com.br"
    # E-mails com papel de Dev (acesso à tela de gerenciamento, junto do admin).
    dev_emails: str = ""
    # SMTP opcional para notificar falhas de jobs agendados. Sem host, não envia.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "flowdesk@irko.com.br"
    notify_emails: str = ""  # destinatários, separados por vírgula

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    @property
    def dev_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.dev_emails.split(",") if e.strip()}

    @property
    def db_url(self) -> str:
        """URL do banco a usar. Prefere Postgres (Supabase) se configurado."""
        return (self.supabase_db_url or self.database_url).strip()

    @property
    def python_executable(self) -> str:
        """Interpreter used to run user scripts in subprocess."""
        return self.script_python.strip() or sys.executable

    @property
    def ai_enabled(self) -> bool:
        return bool(self.openai_api_key.strip())


settings = Settings()
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
