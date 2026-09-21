from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import StreamingResponse

from mi_llama import __version__
from mi_llama.config import Settings
from mi_llama.conversations import ConversationService
from mi_llama.domain import (
    Conversation,
    ConversationWithMessages,
    CreateConversationRequest,
    ModelInfo,
    ProviderHealth,
    SendMessageRequest,
)
from mi_llama.persistence import ConversationRepository
from mi_llama.providers.base import ModelProvider
from mi_llama.providers.errors import ProviderError
from mi_llama.providers.ollama import OllamaProvider


def create_app(
    *,
    settings: Settings | None = None,
    provider: ModelProvider | None = None,
    repository: ConversationRepository | None = None,
) -> FastAPI:
    runtime_settings = settings or Settings()
    runtime_settings.ensure_runtime_directories()

    runtime_repository = repository or ConversationRepository(runtime_settings.database_path)
    runtime_provider = provider or OllamaProvider(
        base_url=str(runtime_settings.ollama_base_url),
        request_timeout_seconds=runtime_settings.request_timeout_seconds,
        connect_timeout_seconds=runtime_settings.connect_timeout_seconds,
    )
    conversation_service = ConversationService(
        repository=runtime_repository,
        provider=runtime_provider,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await runtime_repository.initialize()
        try:
            yield
        finally:
            await runtime_provider.close()

    app = FastAPI(
        title=runtime_settings.app_name,
        version=__version__,
        description="Local-first AI knowledge and data studio API.",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        provider_health = await runtime_provider.health()
        return {
            "app": "ready",
            "version": __version__,
            "provider": provider_health.model_dump(mode="json"),
        }

    @app.get("/api/provider/health", response_model=ProviderHealth)
    async def provider_health() -> ProviderHealth:
        return await runtime_provider.health()

    @app.get("/api/models", response_model=list[ModelInfo])
    async def list_models() -> list[ModelInfo]:
        try:
            return await runtime_provider.list_models()
        except ProviderError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc

    @app.get("/api/conversations", response_model=list[Conversation])
    async def list_conversations() -> list[Conversation]:
        return await runtime_repository.list_conversations()

    @app.post(
        "/api/conversations",
        response_model=Conversation,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_conversation(request: CreateConversationRequest) -> Conversation:
        return await runtime_repository.create_conversation(
            model=request.model,
            title=request.title,
        )

    @app.get(
        "/api/conversations/{conversation_id}",
        response_model=ConversationWithMessages,
    )
    async def get_conversation(conversation_id: UUID) -> ConversationWithMessages:
        result = await conversation_service.get_conversation(conversation_id)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
        return result

    @app.post("/api/conversations/{conversation_id}/messages")
    async def stream_message(
        conversation_id: UUID,
        request: SendMessageRequest,
    ) -> StreamingResponse:
        existing = await conversation_service.get_conversation(conversation_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

        async def generate() -> AsyncIterator[str]:
            try:
                async for token in conversation_service.stream_reply(
                    conversation_id=conversation_id,
                    user_content=request.content,
                ):
                    yield json.dumps({"type": "token", "content": token}) + "\n"
                yield json.dumps({"type": "done"}) + "\n"
            except ProviderError as exc:
                yield json.dumps({"type": "error", "error": str(exc)}) + "\n"

        return StreamingResponse(
            generate(),
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-cache"},
        )

    return app


app = create_app()


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
