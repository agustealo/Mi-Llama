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
