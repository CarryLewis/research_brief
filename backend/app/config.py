from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: str = "state"
    thinking_vault_path: str = "vault"
    thinking_notes_folder: str = "Thinking"
    thinking_archive_folder: str = "Archive/Thinking"
    notion_token: str = ""
    notion_thinking_database_id: str = ""

    @property
    def data_path(self) -> Path:
        path = Path(self.data_dir)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def db_path(self) -> Path:
        return self.data_path / "thinking_sync.db"

    @property
    def resolved_thinking_vault_path(self) -> str:
        raw = (self.thinking_vault_path or "").strip()
        if not raw:
            return ""
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return str(path)


@lru_cache
def get_settings() -> Settings:
    return Settings()
