from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Protocol, runtime_checkable
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from mi_llama.repositories import RepositoryError
from mi_llama.research_structure.models import (
    CitationCandidate,
    ClaimEvidence,
    EvidenceStance,
    ResearchClaim,
)
from mi_llama.writing_structure.models import ManuscriptRevision, WritingResearchLink
from mi_llama.writing_studio.models import ManuscriptDraft
from mi_llama.writing_studio.repository import SupabaseWritingStudioRepository


class PromoteWritingEvidenceRequest(BaseModel):
    promotion_id: UUID
    revision_id: UUID
    expected_draft_version: int = Field(ge=1)
    selection_start: int = Field(ge=0)
    selection_end: int = Field(ge=1)
    chunk_id: UUID
    stance: EvidenceStance
    note: str | None = Field(default=None, max_length=8000)

    @model_validator(mode="after")
    def validate_selection(self) -> PromoteWritingEvidenceRequest:
        if self.selection_end <= self.selection_start:
            raise ValueError("selection_end must be greater than selection_start")
        return self


class WritingEvidencePromotionResult(BaseModel):
    draft: ManuscriptDraft
    revision: ManuscriptRevision
    claim: ResearchClaim
    evidence: ClaimEvidence
    citation: CitationCandidate
    claim_link: WritingResearchLink
    evidence_link: WritingResearchLink


class WritingEvidenceConflict(RuntimeError):
    """The draft/revision identity changed before evidence could be promoted."""


class WritingEvidenceValidationError(RuntimeError):
    """The requested manuscript evidence promotion is invalid."""


class WritingEvidenceNotFound(RuntimeError):
    """A required manuscript or source entity is not visible to the caller."""


@runtime_checkable
class WritingEvidenceRepository(Protocol):
    async def promote_writing_evidence(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        request: PromoteWritingEvidenceRequest,
    ) -> WritingEvidencePromotionResult: ...


class SupabaseWritingEvidenceRepository(SupabaseWritingStudioRepository):
    """Writing-studio repository with atomic passage evidence promotion."""

    async def promote_writing_evidence(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        request: PromoteWritingEvidenceRequest,
    ) -> WritingEvidencePromotionResult:
        rows = await self._request_rows(
            "POST",
            "/rpc/promote_writing_evidence",
            access_token=access_token,
            json={
                "p_project_id": str(project_id),
                "p_document_id": str(document_id),
                "p_promotion_id": str(request.promotion_id),
                "p_revision_id": str(request.revision_id),
                "p_expected_draft_version": request.expected_draft_version,
                "p_selection_start": request.selection_start,
                "p_selection_end": request.selection_end,
                "p_chunk_id": str(request.chunk_id),
                "p_stance": request.stance.value,
                "p_note": request.note,
            },
        )
        return self._one(rows, WritingEvidencePromotionResult)


def _map_repository_error(exc: RepositoryError) -> RuntimeError | None:
    message = str(exc)
    lowered = message.lower()
    if any(
        marker in lowered
        for marker in (
            "version is stale",
            "draft version",
            "current draft base",
            "revision no longer matches",
        )
    ):
        return WritingEvidenceConflict(message)
    if "not found" in lowered:
        return WritingEvidenceNotFound(message)
    if any(
        marker in lowered
        for marker in (
            "selection",
            "passage",
            "stance",
            "promotion id",
            "maximum",
        )
    ):
        return WritingEvidenceValidationError(message)
    return None


def register_writing_evidence_routes(
    *,
    app: FastAPI,
    repository: WritingEvidenceRepository,
    access_token_dependency: Callable[..., str],
) -> None:
    @app.post(
        "/api/projects/{project_id}/writing/documents/{document_id}/research/promotions",
        response_model=WritingEvidencePromotionResult,
        status_code=status.HTTP_201_CREATED,
    )
    async def promote_writing_evidence(
        project_id: UUID,
        document_id: UUID,
        request: PromoteWritingEvidenceRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> WritingEvidencePromotionResult:
        try:
            return await repository.promote_writing_evidence(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                request=request,
            )
        except RepositoryError as exc:
            mapped = _map_repository_error(exc)
            if isinstance(mapped, WritingEvidenceConflict):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail=str(mapped)
                ) from exc
            if isinstance(mapped, WritingEvidenceNotFound):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail=str(mapped)
                ) from exc
            if isinstance(mapped, WritingEvidenceValidationError):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=str(mapped)
                ) from exc
            raise
