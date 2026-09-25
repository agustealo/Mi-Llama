from __future__ import annotations

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status

from mi_llama.providers.base import StructuredModelProvider
from mi_llama.providers.errors import ProviderError
from mi_llama.writing_studio.models import (
    ApplyWritingProposalRequest,
    CreateWritingProposalRequest,
    ManuscriptDraft,
    SaveManuscriptDraftRequest,
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
from mi_llama.writing_structure.models import WritingStructureNotFound


def register_writing_studio_routes(
    *,
    app: FastAPI,
    repository: WritingStudioRepository,
    provider: StructuredModelProvider,
    access_token_dependency: Callable[..., str],
) -> None:
    service = WritingStudioService(repository=repository, provider=provider)

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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manuscript not found") from exc

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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manuscript not found") from exc

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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manuscript not found") from exc
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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Writing proposal not found") from exc
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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Writing proposal not found") from exc
        except WritingProposalStale as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except WritingStudioValidationError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
