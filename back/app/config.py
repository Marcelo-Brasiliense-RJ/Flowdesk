"""Application configuration loaded from environment / .env."""
from __future__ import annotations

import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACK_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BACK_DIR / "storage"
DB_PATH = BACK_DIR / "flowdesk.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACK_DIR / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    secret_key: str = "flowdesk-dev-secret"
    access_token_expire_minutes: int = 60 * 24 * 7
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    script_python: str = ""
    frontend_origin: str = "http://localhost:5173"

    @property
    def python_executable(self) -> str:
        """Interpreter used to run user scripts in subprocess."""
        return self.script_python.strip() or sys.executable

    @property
    def ai_enabled(self) -> bool:
        return bool(self.openai_api_key.strip())


settings = Settings()
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
