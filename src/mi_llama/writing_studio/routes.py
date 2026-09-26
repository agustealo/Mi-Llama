from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from typing import Annotated, cast
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import StreamingResponse

from mi_llama.conversations import (
    ConversationContextConflict,
    ConversationContextError,
    ConversationContextUnavailable,
    ConversationService,
)
from mi_llama.domain import Conversation
from mi_llama.providers.base import ModelProvider, StructuredModelProvider
from mi_llama.providers.errors import ProviderError
from mi_llama.repositories import RepositoryError
from mi_llama.writing_structure.models import WritingStructureNotFound
from mi_llama.writing_studio.models import (
    ApplyWritingProposalRequest,
    CheckpointManuscriptDraftRequest,
    CheckpointManuscriptDraftResult,
    CreateDocumentConversationRequest,
    CreateWritingProposalRequest,
    ManuscriptDraft,
    SaveManuscriptDraftRequest,
    SendDocumentConversationMessageRequest,
    WritingProposal,
    WritingProposalApplicationResult,
)
from mi_llama.writing_studio.repository import WritingStudioRepository
from mi_llama.writing_studio.service import (
    DraftVersionConflict,
    WritingProposalStale,
    WritingStudioService,
    WritingStudioValidationError,
)


def register_writing_studio_routes(
    *,
    app: FastAPI,
    repository: WritingStudioRepository,
    provider: StructuredModelProvider,
    access_token_dependency: Callable[..., str],
) -> None:
    service = WritingStudioService(repository=repository, provider=provider)
    conversation_service = ConversationService(
        repository=repository,
        provider=cast(ModelProvider, provider),
    )

    @app.get(
        "/api/projects/{project_id}/writing/documents/{document_id}/conversations",
        response_model=list[Conversation],
    )
    async def list_document_conversations(
        project_id: UUID,
        document_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> list[Conversation]:
        document = await repository.get_manuscript_document(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Manuscript document not found"
            )
        conversations = await repository.list_conversations(
            access_token=access_token,
            project_id=project_id,
        )
        return [item for item in conversations if item.document_id == document_id]

    @app.post(
        "/api/projects/{project_id}/writing/documents/{document_id}/conversations",
        response_model=Conversation,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_document_conversation(
        project_id: UUID,
        document_id: UUID,
        request: CreateDocumentConversationRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> Conversation:
        document = await repository.get_manuscript_document(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Manuscript document not found"
            )
        try:
            return await conversation_service.create_conversation(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                model=request.model,
                title=request.title,
            )
        except ConversationContextUnavailable as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
            ) from exc

    @app.post(
        "/api/projects/{project_id}/writing/documents/{document_id}/conversations/{conversation_id}/messages"
    )
    async def stream_document_conversation_message(
        project_id: UUID,
        document_id: UUID,
        conversation_id: UUID,
        request: SendDocumentConversationMessageRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> StreamingResponse:
        existing = await conversation_service.get_conversation(
            access_token=access_token,
            conversation_id=conversation_id,
        )
        if (
            existing is None
            or existing.conversation.project_id != project_id
            or existing.conversation.document_id != document_id
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Manuscript conversation not found",
            )
        try:
            context = await conversation_service.prepare_turn_context(
                access_token=access_token,
                conversation=existing.conversation,
                request=request.context,
            )
        except ConversationContextConflict as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except ConversationContextUnavailable as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
            ) from exc
        except ConversationContextError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        async def generate() -> AsyncIterator[str]:
            try:
                async for token in conversation_service.stream_reply(
                    access_token=access_token,
                    conversation_id=conversation_id,
                    user_content=request.content,
                    context=context,
                ):
                    yield json.dumps({"type": "token", "content": token}) + "\n"
                yield json.dumps({"type": "done"}) + "\n"
            except (ConversationContextError, ProviderError, RepositoryError) as exc:
                yield json.dumps({"type": "error", "error": str(exc)}) + "\n"

        return StreamingResponse(
            generate(),
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-cache"},
        )

    @app.get(
        "/api/projects/{project_id}/writing/documents/{document_id}/draft",
        response_model=ManuscriptDraft | None,
    )
    async def get_manuscript_draft(
        project_id: UUID,
        document_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> ManuscriptDraft | None:
        try:
            return await service.get_draft(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
            )
        except WritingStructureNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Manuscript not found"
            ) from exc

    @app.put(
        "/api/projects/{project_id}/writing/documents/{document_id}/draft",
        response_model=ManuscriptDraft,
    )
    async def save_manuscript_draft(
        project_id: UUID,
        document_id: UUID,
        request: SaveManuscriptDraftRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> ManuscriptDraft:
        try:
            return await service.save_draft(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                request=request,
            )
        except WritingStructureNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Manuscript document or base revision not found",
            ) from exc
        except DraftVersionConflict as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @app.post(
        "/api/projects/{project_id}/writing/documents/{document_id}/draft/checkpoint",
        response_model=CheckpointManuscriptDraftResult,
        status_code=status.HTTP_201_CREATED,
    )
    async def checkpoint_manuscript_draft(
        project_id: UUID,
        document_id: UUID,
        request: CheckpointManuscriptDraftRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> CheckpointManuscriptDraftResult:
        try:
            return await service.checkpoint_draft(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                request=request,
            )
        except WritingStructureNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Manuscript document not found",
            ) from exc
        except DraftVersionConflict as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except WritingStudioValidationError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.get(
        "/api/projects/{project_id}/writing/documents/{document_id}/proposals",
        response_model=list[WritingProposal],
    )
    async def list_writing_proposals(
        project_id: UUID,
        document_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> list[WritingProposal]:
        try:
            return await service.list_proposals(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
            )
        except WritingStructureNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Manuscript not found"
            ) from exc

    @app.post(
        "/api/projects/{project_id}/writing/documents/{document_id}/proposals",
        response_model=WritingProposal,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_writing_proposal(
        project_id: UUID,
        document_id: UUID,
        request: CreateWritingProposalRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> WritingProposal:
        try:
            return await service.create_proposal(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                request=request,
            )
        except WritingStructureNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Manuscript not found"
            ) from exc
        except DraftVersionConflict as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except WritingStudioValidationError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except ProviderError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    @app.post(
        "/api/projects/{project_id}/writing/documents/{document_id}/proposals/{proposal_id}/accept",
        response_model=WritingProposalApplicationResult,
    )
    async def accept_writing_proposal(
        project_id: UUID,
        document_id: UUID,
        proposal_id: UUID,
        request: ApplyWritingProposalRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> WritingProposalApplicationResult:
        try:
            return await service.accept_proposal(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                proposal_id=proposal_id,
                request=request,
            )
        except WritingStructureNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Writing proposal not found",
            ) from exc
        except WritingProposalStale as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except WritingStudioValidationError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.post(
        "/api/projects/{project_id}/writing/documents/{document_id}/proposals/{proposal_id}/reject",
        response_model=WritingProposal,
    )
    async def reject_writing_proposal(
        project_id: UUID,
        document_id: UUID,
        proposal_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> WritingProposal:
        try:
            return await service.reject_proposal(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                proposal_id=proposal_id,
            )
        except WritingStructureNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Writing proposal not found",
            ) from exc
        except WritingProposalStale as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except WritingStudioValidationError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
