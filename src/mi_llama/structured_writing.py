from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Annotated, Any, Self
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from mi_llama.domain import LearningEvent
from mi_llama.editor_state import EditorStateError, validate_editor_state
from mi_llama.repositories import RepositoryError
from mi_llama.writing_structure.models import WritingStructureNotFound
from mi_llama.writing_studio.models import (
    ManuscriptDraft,
    WritingProposal,
    WritingProposalApplicationResult,
    WritingProposalStatus,
)
from mi_llama.writing_studio.repository import WritingStudioRepository
from mi_llama.writing_studio.service import WritingProposalStale, WritingStudioValidationError


class ApplyStructuredWritingProposalRequest(BaseModel):
    expected_draft_version: int = Field(ge=1)
    editor_state: dict[str, Any]
    plain_text: str = Field(max_length=2_000_000)

    @model_validator(mode="after")
    def validate_projection(self) -> Self:
        try:
            validate_editor_state(self.editor_state, self.plain_text)
        except EditorStateError as exc:
            raise ValueError(str(exc)) from exc
        return self


class StructuredWritingService:
    def __init__(self, *, repository: WritingStudioRepository) -> None:
        self._repository = repository

    async def accept_proposal(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        proposal_id: UUID,
        request: ApplyStructuredWritingProposalRequest,
    ) -> WritingProposalApplicationResult:
        proposal = await self._require_proposal(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            proposal_id=proposal_id,
        )
        if proposal.status is not WritingProposalStatus.PROPOSED:
            raise WritingProposalStale("Only a proposed edit can be accepted")

        draft = await self._repository.get_manuscript_draft(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        if draft is None:
            raise WritingProposalStale("The draft no longer exists")
        if (
            draft.version != request.expected_draft_version
            or proposal.base_draft_version != request.expected_draft_version
        ):
            raise WritingProposalStale("The draft changed after this proposal was created")

        self._validate_selection(draft=draft, proposal=proposal)
        expected_plain_text = (
            draft.plain_text[: proposal.selection_start]
            + proposal.proposed_text
            + draft.plain_text[proposal.selection_end :]
        )
        if request.plain_text != expected_plain_text:
            raise WritingStudioValidationError(
                "Structured proposal application does not match the reviewed replacement"
            )

        try:
            updated_draft = await self._repository.apply_writing_proposal(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                proposal_id=proposal_id,
                expected_draft_version=request.expected_draft_version,
                editor_state=request.editor_state,
                plain_text=request.plain_text,
            )
        except RepositoryError as exc:
            message = str(exc).lower()
            if "stale" in message or "version" in message or "selection" in message:
                raise WritingProposalStale(str(exc)) from exc
            raise

        accepted = await self._require_proposal(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            proposal_id=proposal_id,
        )
        if accepted.status is not WritingProposalStatus.ACCEPTED:
            raise WritingProposalStale("Proposal application did not commit acceptance")

        await self._repository.add_learning_signal(
            access_token=access_token,
            project_id=project_id,
            event_type=LearningEvent.AI_EDIT_ACCEPTED,
            entity_type="writing_proposal",
            entity_id=proposal_id,
            metadata={
                "operation": proposal.operation.value,
                "model": proposal.model,
                "base_draft_version": proposal.base_draft_version,
                "applied_draft_version": updated_draft.version,
                "editor_schema": request.editor_state.get("schema"),
            },
        )
        return WritingProposalApplicationResult(draft=updated_draft, proposal=accepted)

    async def _require_proposal(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        proposal_id: UUID,
    ) -> WritingProposal:
        proposal = await self._repository.get_writing_proposal(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            proposal_id=proposal_id,
        )
        if proposal is None:
            raise WritingStructureNotFound(str(proposal_id))
        return proposal

    @staticmethod
    def _validate_selection(*, draft: ManuscriptDraft, proposal: WritingProposal) -> None:
        if proposal.selection_start < 0 or proposal.selection_end > len(draft.plain_text):
            raise WritingProposalStale("The proposal selection no longer fits the draft")
        if proposal.selection_end <= proposal.selection_start:
            raise WritingProposalStale("The proposal selection is invalid")
        current = draft.plain_text[proposal.selection_start : proposal.selection_end]
        if current != proposal.original_text or _sha256(current) != proposal.selection_hash:
            raise WritingProposalStale(
                "The selected passage changed after this proposal was created"
            )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def register_structured_writing_routes(
    *,
    app: FastAPI,
    repository: WritingStudioRepository,
    access_token_dependency: Callable[..., str],
) -> None:
    service = StructuredWritingService(repository=repository)

    @app.post(
        "/api/projects/{project_id}/writing/documents/{document_id}/proposals/{proposal_id}/accept-structured",
        response_model=WritingProposalApplicationResult,
    )
    async def accept_structured_writing_proposal(
        project_id: UUID,
        document_id: UUID,
        proposal_id: UUID,
        request: ApplyStructuredWritingProposalRequest,
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
