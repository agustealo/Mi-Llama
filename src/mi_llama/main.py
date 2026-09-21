from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any
from uuid import UUID

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from mi_llama import __version__
from mi_llama.config import Settings
from mi_llama.conversations import ConversationService
from mi_llama.domain import (
    Conversation,
    ConversationWithMessages,
    CreateConversationRequest,
    CreateLearningSignalRequest,
    CreateProjectRequest,
    LearningSignal,
    ModelInfo,
    Project,
    ProviderHealth,
    SendMessageRequest,
)
from mi_llama.providers.base import ModelProvider
from mi_llama.providers.errors import ProviderError
from mi_llama.providers.ollama import OllamaProvider
from mi_llama.repositories import (
    Repository,
    RepositoryAuthenticationError,
    RepositoryAuthorizationError,
    RepositoryError,
    SupabaseRepository,
)

_bearer = HTTPBearer(auto_error=False)


def require_access_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A Supabase bearer token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


def create_app(
    *,
    settings: Settings | None = None,
    provider: ModelProvider | None = None,
    repository: Repository | None = None,
) -> FastAPI:
    runtime_settings = settings or Settings()

    if repository is None:
        supabase_url, publishable_key = runtime_settings.require_supabase()
        runtime_repository: Repository = SupabaseRepository(
            supabase_url=supabase_url,
            publishable_key=publishable_key,
            timeout_seconds=runtime_settings.request_timeout_seconds,
        )
    else:
        runtime_repository = repository

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
        try:
            yield
        finally:
            await runtime_provider.close()
            await runtime_repository.close()

    app = FastAPI(
        title=runtime_settings.app_name,
        version=__version__,
        description="AI research and writing studio API.",
        lifespan=lifespan,
    )

    @app.exception_handler(RepositoryAuthenticationError)
    async def repository_authentication_error(
        _: Any, exc: RepositoryAuthenticationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": str(exc)},
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(RepositoryAuthorizationError)
    async def repository_authorization_error(
        _: Any, exc: RepositoryAuthorizationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": str(exc)},
        )

    @app.exception_handler(RepositoryError)
    async def repository_error(_: Any, exc: RepositoryError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": str(exc)},
        )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        provider_health = await runtime_provider.health()
        return {
            "app": "ready",
            "version": __version__,
            "provider": provider_health.model_dump(mode="json"),
            "persistence": "supabase",
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

    @app.get("/api/projects", response_model=list[Project])
    async def list_projects(
        access_token: Annotated[str, Depends(require_access_token)],
    ) -> list[Project]:
        return await runtime_repository.list_projects(access_token=access_token)

    @app.post("/api/projects", response_model=Project, status_code=status.HTTP_201_CREATED)
    async def create_project(
        request: CreateProjectRequest,
        access_token: Annotated[str, Depends(require_access_token)],
    ) -> Project:
        return await runtime_repository.create_project(
            access_token=access_token,
            title=request.title,
            description=request.description,
        )

    @app.get("/api/projects/{project_id}", response_model=Project)
    async def get_project(
        project_id: UUID,
        access_token: Annotated[str, Depends(require_access_token)],
    ) -> Project:
        project = await runtime_repository.get_project(
            access_token=access_token,
            project_id=project_id,
        )
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        return project

    @app.get("/api/projects/{project_id}/conversations", response_model=list[Conversation])
    async def list_conversations(
        project_id: UUID,
        access_token: Annotated[str, Depends(require_access_token)],
    ) -> list[Conversation]:
        return await runtime_repository.list_conversations(
            access_token=access_token,
            project_id=project_id,
        )

    @app.post(
        "/api/projects/{project_id}/conversations",
        response_model=Conversation,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_conversation(
        project_id: UUID,
        request: CreateConversationRequest,
        access_token: Annotated[str, Depends(require_access_token)],
    ) -> Conversation:
        return await runtime_repository.create_conversation(
            access_token=access_token,
            project_id=project_id,
            model=request.model,
            title=request.title,
        )

    @app.get(
        "/api/conversations/{conversation_id}",
        response_model=ConversationWithMessages,
    )
    async def get_conversation(
        conversation_id: UUID,
        access_token: Annotated[str, Depends(require_access_token)],
    ) -> ConversationWithMessages:
        result = await conversation_service.get_conversation(
            access_token=access_token,
            conversation_id=conversation_id,
        )
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
        access_token: Annotated[str, Depends(require_access_token)],
    ) -> StreamingResponse:
        existing = await conversation_service.get_conversation(
            access_token=access_token,
            conversation_id=conversation_id,
        )
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

        async def generate() -> AsyncIterator[str]:
            try:
                async for token in conversation_service.stream_reply(
                    access_token=access_token,
                    conversation_id=conversation_id,
                    user_content=request.content,
                ):
                    yield json.dumps({"type": "token", "content": token}) + "\n"
                yield json.dumps({"type": "done"}) + "\n"
            except (ProviderError, RepositoryError) as exc:
                yield json.dumps({"type": "error", "error": str(exc)}) + "\n"

        return StreamingResponse(
            generate(),
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-cache"},
        )

    @app.post(
        "/api/projects/{project_id}/learning-signals",
        response_model=LearningSignal,
        status_code=status.HTTP_201_CREATED,
    )
    async def add_learning_signal(
        project_id: UUID,
        request: CreateLearningSignalRequest,
        access_token: Annotated[str, Depends(require_access_token)],
    ) -> LearningSignal:
        return await runtime_repository.add_learning_signal(
            access_token=access_token,
            project_id=project_id,
            event_type=request.event_type,
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            metadata=request.metadata,
        )

    return app


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
