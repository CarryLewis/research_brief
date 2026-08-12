from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_ROOT.parent
CONFIGS_DIR = BACKEND_ROOT / "configs"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: str = "openai"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    ncbi_email: str = "research-brief@localhost"
    ncbi_api_key: str = ""

    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    imap_user: str = ""
    imap_password: str = ""
    imap_folder: str = "INBOX"

    # Inbound email webhook (push)
    inbound_webhook_secret: str = ""
    inbound_notebook_id: str = ""
    inbound_max_links: int = 3
    inbound_topic: str = "订阅收件"
    # open = accept all senders (tag if catalog match); allowlist = only enabled catalog matches
    subscription_mode: str = "open"

    # Digest → main inbox (SMTP)
    digest_to: str = ""
    digest_from: str = ""
    digest_language: str = "zh"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True

    data_dir: str = str(PROJECT_ROOT / "data")
    content_lake_dir: str = ""
    default_vault_path: str = ""
    # Shared token for browser extension ↔ local API (Bearer / X-Library-Token)
    library_api_token: str = ""

    # Thinking Vault — Notion → Obsidian (one-way)
    notion_token: str = ""
    notion_thinking_database_id: str = ""

    host: str = "127.0.0.1"
    port: int = 8000

    @property
    def data_path(self) -> Path:
        path = Path(self.data_dir)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def db_path(self) -> Path:
        return self.data_path / "research_brief.db"

    @property
    def content_lake_path(self) -> Path:
        if self.content_lake_dir:
            path = Path(self.content_lake_dir)
            if not path.is_absolute():
                path = PROJECT_ROOT / path
        else:
            path = self.data_path / "content_lake"
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()
