from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

from mi_llama.config import Settings
from mi_llama.domain import ChatMessage, ModelInfo, ProviderHealth, ProviderStatus
from mi_llama.main import create_app


class StructuredProviderStub:
    async def health(self) -> ProviderHealth:
        return ProviderHealth(status=ProviderStatus.READY)

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(name="llama3.2:latest")]

    async def chat(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage],
    ) -> str:
        return "unused"

    async def chat_stream(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage],
    ) -> AsyncIterator[str]:
        if False:
            yield "unused"

    async def chat_json(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage],
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        return {}

    async def close(self) -> None:
        return None


class StorageStub:
    async def close(self) -> None:
        return None

    async def upload(
        self,
        *,
        access_token: str,
        bucket: str,
        path: str,
        media_type: str,
        content: bytes,
    ) -> None:
        return None

    async def delete(
        self,
        *,
        access_token: str,
        bucket: str,
        path: str,
    ) -> None:
        return None


def test_default_runtime_mounts_writing_studio_authority() -> None:
    app = create_app(
        settings=Settings(
            _env_file=None,
            supabase_url="https://example.supabase.co",
            supabase_publishable_key="test-publishable-key",
        ),
        provider=StructuredProviderStub(),
        storage=StorageStub(),
    )

    routes = {
        (route.path, method)
        for route in app.routes
        for method in (getattr(route, "methods", None) or set())
    }

    document = "/api/projects/{project_id}/writing/documents/{document_id}"
    assert (f"{document}/draft", "GET") in routes
    assert (f"{document}/draft", "PUT") in routes
    assert (f"{document}/draft/checkpoint", "POST") in routes
    assert (f"{document}/proposals", "GET") in routes
    assert (f"{document}/proposals", "POST") in routes
    assert (f"{document}/proposals/{{proposal_id}}/accept", "POST") in routes
    assert (f"{document}/proposals/{{proposal_id}}/reject", "POST") in routes
    assert (f"{document}/conversations", "GET") in routes
    assert (f"{document}/conversations", "POST") in routes
    assert (f"{document}/conversations/{{conversation_id}}/messages", "POST") in routes
