from __future__ import annotations

from pathlib import Path

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the local Mi-Llama service."""

    model_config = SettingsConfigDict(
        env_prefix="MI_LLAMA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Mi-Llama"
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65535)
    ollama_base_url: AnyHttpUrl = "http://127.0.0.1:11434"
    request_timeout_seconds: float = Field(default=60.0, gt=0)
    connect_timeout_seconds: float = Field(default=3.0, gt=0)
    data_dir: Path = Path.home() / ".mi-llama"
    database_name: str = "mi-llama.sqlite3"

    @property
    def database_path(self) -> Path:
        return self.data_dir / self.database_name

    def ensure_runtime_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
