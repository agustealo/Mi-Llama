from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.staticfiles import StaticFiles

from mi_llama.config import Settings
from mi_llama.main import create_app as create_api_app

_WORKSPACE_ROOT = Path(__file__).with_name("workspace_assets")


def attach_workspace(app: FastAPI) -> FastAPI:
    """Attach the repository-owned Mi-Llama workspace shell to an API application."""
    if not _WORKSPACE_ROOT.is_dir():
        raise RuntimeError(f"Mi-Llama workspace assets are missing: {_WORKSPACE_ROOT}")
    app.mount("/", StaticFiles(directory=_WORKSPACE_ROOT, html=True), name="workspace")
    return app


def create_app(*, settings: Settings | None = None) -> FastAPI:
    """Create the normal Mi-Llama API and attach its consumer workspace shell."""
    runtime_settings = settings or Settings()
    app = create_api_app(settings=runtime_settings)

    @app.get("/api/client-config")
    async def client_config() -> dict[str, str]:
        if (
            runtime_settings.supabase_url is None
            or runtime_settings.supabase_publishable_key is None
        ):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Supabase authentication is not configured",
            )
        return {
            "supabase_url": str(runtime_settings.supabase_url).rstrip("/"),
            "supabase_publishable_key": (
                runtime_settings.supabase_publishable_key.get_secret_value()
            ),
        }

    return attach_workspace(app)


def run() -> None:
    settings = Settings()
    uvicorn.run(
        create_app(settings=settings),
        host=settings.host,
        port=settings.port,
        log_level="info",
    )


if __name__ == "__main__":
    run()
