from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any
from uuid import UUID

import uvicorn
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from mi_llama import __version__
from mi_llama.config import Settings
from mi_llama.conversations import ConversationService
from mi_llama.documents import DocumentExtractionError
from mi_llama.domain import (
    Conversation,
    ConversationWithMessages,
    CreateConversationRequest,
    CreateLearningSignalRequest,
    CreateProjectRequest,
    LearningEvent,
    LearningSignal,
    ModelInfo,
    Project,
    ProviderHealth,
    ResearchQueryRequest,
    ResearchResponse,
    SendMessageRequest,
    Source,
    SourceIngestResult,
    SourceVersion,
)
from mi_llama.providers.base import ModelProvider
from mi_llama.providers.errors import ProviderError
from mi_llama.providers.ollama import OllamaProvider
from mi_llama.repositories import (
    Repository,
    RepositoryAuthenticationError,
    RepositoryAuthorizationError,
    RepositoryError,
)
from mi_llama.research import (
    AuthorizedResearchService,
    MindsDBResearchEngine,
    ResearchEngine,
    ResearchError,
)
from mi_llama.research_structure import (
    ResearchStructureRepository,
    register_research_structure_routes,
)
from mi_llama.sources import SourceIngestError, SourceProcessingError, SourceService
from mi_llama.storage import SOURCE_BUCKET, ObjectStorage, SupabaseStorage
from mi_llama.writing_structure import (
    SupabaseWritingRepository,
    WritingRepository,
    register_writing_structure_routes,
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
    storage: ObjectStorage | None = None,
    research_engine: ResearchEngine | None = None,
) -> FastAPI:
    runtime_settings = settings or Settings()
    configured_supabase: tuple[str, str] | None = None

    if repository is None:
        configured_supabase = runtime_settings.require_supabase()
        supabase_url, publishable_key = configured_supabase
        runtime_repository: Repository = SupabaseWritingRepository(
            supabase_url=supabase_url,
            publishable_key=publishable_key,
            timeout_seconds=runtime_settings.request_timeout_seconds,
        )
    else:
        runtime_repository = repository

    if storage is not None:
        runtime_storage: ObjectStorage | None = storage
    else:
        if configured_supabase is None:
            try:
                configured_supabase = runtime_settings.require_supabase()
            except RuntimeError:
                configured_supabase = None
        if configured_supabase is None:
            runtime_storage = None
        else:
            supabase_url, publishable_key = configured_supabase
            runtime_storage = SupabaseStorage(
                supabase_url=supabase_url,
                publishable_key=publishable_key,
                timeout_seconds=runtime_settings.request_timeout_seconds,
            )

    runtime_provider = provider or OllamaProvider(
        base_url=str(runtime_settings.ollama_base_url),
        request_timeout_seconds=runtime_settings.request_timeout_seconds,
        connect_timeout_seconds=runtime_settings.connect_timeout_seconds,
    )

    if research_engine is not None:
        runtime_research: ResearchEngine | None = research_engine
    elif runtime_settings.mindsdb_enabled:
        runtime_research = MindsDBResearchEngine(
            base_url=str(runtime_settings.mindsdb_base_url),
            project_name=runtime_settings.mindsdb_project,
            embedding_model=runtime_settings.mindsdb_embedding_model,
            embedding_base_url=runtime_settings.mindsdb_embedding_url(),
            timeout_seconds=runtime_settings.request_timeout_seconds,
            api_token=runtime_settings.mindsdb_token(),
        )
    else:
        runtime_research = None

    conversation_service = ConversationService(
        repository=runtime_repository,
        provider=runtime_provider,
    )
    source_service = (
        None
        if runtime_storage is None
        else SourceService(
            repository=runtime_repository,
            storage=runtime_storage,
            bucket=SOURCE_BUCKET,
            max_bytes=runtime_settings.source_max_bytes,
            max_extracted_chars=runtime_settings.source_max_extracted_chars,
            chunk_chars=runtime_settings.source_chunk_chars,
            chunk_overlap_chars=runtime_settings.source_chunk_overlap_chars,
            research=runtime_research,
        )
    )
    research_service = (
        None
        if runtime_research is None
        else AuthorizedResearchService(repository=runtime_repository, engine=runtime_research)
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await runtime_provider.close()
            await runtime_repository.close()
            if runtime_storage is not None:
                await runtime_storage.close()
            if runtime_research is not None:
                await runtime_research.close()

    app = FastAPI(
        title=runtime_settings.app_name,
        version=__version__,
        description="AI research and writing studio API.",
        lifespan=lifespan,
    )

    if isinstance(runtime_repository, ResearchStructureRepository):
        register_research_structure_routes(
            app=app,
            repository=runtime_repository,
            research=research_service,
            access_token_dependency=require_access_token,
        )

    if isinstance(runtime_repository, WritingRepository):
        register_writing_structure_routes(
            app=app,
            repository=runtime_repository,
            access_token_dependency=require_access_token,
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

    @app.exception_handler(DocumentExtractionError)
    @app.exception_handler(SourceIngestError)
    async def source_validation_error(_: Any, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": str(exc)},
        )

    @app.exception_handler(SourceProcessingError)
    async def source_processing_error(_: Any, exc: SourceProcessingError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": str(exc)},
        )

    @app.exception_handler(ResearchError)
    async def research_error(_: Any, exc: ResearchError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": str(exc)},
        )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        provider_health = await runtime_provider.health()
        research_health = "disabled"
        if runtime_research is not None:
            research_health = "ready" if await runtime_research.health() else "unavailable"
        return {
            "app": "ready",
            "version": __version__,
            "provider": provider_health.model_dump(mode="json"),
            "persistence": "supabase",
            "storage": "supabase" if runtime_storage is not None else "unavailable",
            "research": research_health,
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

    @app.get("/api/projects/{project_id}/sources", response_model=list[Source])
    async def list_sources(
        project_id: UUID,
        access_token: Annotated[str, Depends(require_access_token)],
    ) -> list[Source]:
        return await runtime_repository.list_sources(
            access_token=access_token,
            project_id=project_id,
        )

    @app.post(
        "/api/projects/{project_id}/sources",
        response_model=SourceIngestResult,
        status_code=status.HTTP_201_CREATED,
    )
    async def upload_source(
        project_id: UUID,
        file: Annotated[UploadFile, File(...)],
        access_token: Annotated[str, Depends(require_access_token)],
    ) -> SourceIngestResult:
        if source_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Supabase Storage is not configured",
            )
        filename = file.filename or "source"
        media_type = file.content_type or "application/octet-stream"
        content = await file.read(runtime_settings.source_max_bytes + 1)
        await file.close()
        try:
            return await source_service.ingest(
                access_token=access_token,
                project_id=project_id,
                filename=filename,
                media_type=media_type,
                content=content,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            ) from exc

    @app.get("/api/projects/{project_id}/sources/{source_id}", response_model=Source)
    async def get_source(
        project_id: UUID,
        source_id: UUID,
        access_token: Annotated[str, Depends(require_access_token)],
    ) -> Source:
        source = await runtime_repository.get_source(
            access_token=access_token,
            source_id=source_id,
        )
        if source is None or source.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
        return source

    @app.post(
        "/api/projects/{project_id}/sources/{source_id}/reindex",
        response_model=SourceVersion,
    )
    async def reindex_source(
        project_id: UUID,
        source_id: UUID,
        access_token: Annotated[str, Depends(require_access_token)],
    ) -> SourceVersion:
        if source_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Research source ingestion is unavailable",
            )
        try:
            return await source_service.reindex(
                access_token=access_token,
                project_id=project_id,
                source_id=source_id,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Source not found"
            ) from exc

    @app.post(
        "/api/projects/{project_id}/research/query",
        response_model=ResearchResponse,
    )
    async def research_query(
        project_id: UUID,
        request: ResearchQueryRequest,
        access_token: Annotated[str, Depends(require_access_token)],
    ) -> ResearchResponse:
        if research_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="MindsDB research is disabled",
            )
        try:
            response = await research_service.query(
                access_token=access_token,
                project_id=project_id,
                query=request.query,
                limit=request.limit,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            ) from exc
        await runtime_repository.add_learning_signal(
            access_token=access_token,
            project_id=project_id,
            event_type=LearningEvent.RESEARCH_RESULT_IMPRESSION,
            entity_type="research_query",
            entity_id=None,
            metadata={
                "hit_count": len(response.hits),
                "chunk_ids": [str(hit.chunk_id) for hit in response.hits],
            },
        )
        return response

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
