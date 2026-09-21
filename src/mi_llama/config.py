from __future__ import annotations

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for Mi-Llama."""

    model_config = SettingsConfigDict(
        env_prefix="MI_LLAMA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Mi-Llama"
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65535)

    ollama_base_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:11434")
    request_timeout_seconds: float = Field(default=60.0, gt=0)
    connect_timeout_seconds: float = Field(default=3.0, gt=0)

    supabase_url: AnyHttpUrl | None = None
    supabase_publishable_key: SecretStr | None = None
    source_max_bytes: int = Field(default=25 * 1024 * 1024, ge=1, le=25 * 1024 * 1024)
    source_max_extracted_chars: int = Field(default=8_000_000, ge=10_000)
    source_chunk_chars: int = Field(default=1600, ge=400, le=8000)
    source_chunk_overlap_chars: int = Field(default=160, ge=0, le=1000)

    mindsdb_enabled: bool = False
    mindsdb_base_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:47334")
    mindsdb_api_token: SecretStr | None = None
    mindsdb_project: str = Field(default="mi_llama", pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$")
    mindsdb_embedding_model: str = Field(default="nomic-embed-text", min_length=1)
    mindsdb_embedding_base_url: AnyHttpUrl | None = None

    def require_supabase(self) -> tuple[str, str]:
        if self.supabase_url is None or self.supabase_publishable_key is None:
            raise RuntimeError(
                "Supabase is not configured. Set MI_LLAMA_SUPABASE_URL and "
                "MI_LLAMA_SUPABASE_PUBLISHABLE_KEY."
            )
        return (
            str(self.supabase_url).rstrip("/"),
            self.supabase_publishable_key.get_secret_value(),
        )

    def mindsdb_token(self) -> str | None:
        if self.mindsdb_api_token is None:
            return None
        return self.mindsdb_api_token.get_secret_value()

    def mindsdb_embedding_url(self) -> str:
        url = self.mindsdb_embedding_base_url or self.ollama_base_url
        return str(url).rstrip("/")
