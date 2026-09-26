from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Protocol, TypeVar, cast, runtime_checkable
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from mi_llama.repositories import RepositoryError
from mi_llama.writing_studio.models import ManuscriptDraft, WritingProposal, WritingProposalStatus

T = TypeVar("T")


class ProvenanceDispositionKind(StrEnum):
    RETIRED = "retired"
    SUPERSEDED = "superseded"
    NEEDS_REGROUNDING = "needs_regrounding"


class ProvenanceDisposition(BaseModel):
    id: UUID
    project_id: UUID
    document_id: UUID
    accepted_proposal_id: UUID
    disposition: ProvenanceDispositionKind
    draft_version: int = Field(ge=1)
    superseding_proposal_id: UUID | None = None
    reason: str | None = Field(default=None, max_length=1000)
    created_by: UUID
    created_at: datetime


class CreateProvenanceDispositionRequest(BaseModel):
    expected_draft_version: int = Field(ge=1)
    disposition: ProvenanceDispositionKind
    superseding_proposal_id: UUID | None = None
    reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_supersession(self) -> CreateProvenanceDispositionRequest:
        if self.disposition is ProvenanceDispositionKind.SUPERSEDED:
            if self.superseding_proposal_id is None:
                raise ValueError("superseded provenance requires a superseding proposal")
        elif self.superseding_proposal_id is not None:
            raise ValueError("superseding_proposal_id is only valid for superseded provenance")
        return self


@runtime_checkable
class ProvenanceDispositionRepository(Protocol):
    async def get_manuscript_draft(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
    ) -> ManuscriptDraft | None: ...

    async def get_writing_proposal(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        proposal_id: UUID,
    ) -> WritingProposal | None: ...

    async def list_provenance_dispositions(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
    ) -> list[ProvenanceDisposition]: ...

    async def create_provenance_disposition(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        accepted_proposal_id: UUID,
        request: CreateProvenanceDispositionRequest,
    ) -> ProvenanceDisposition: ...


class _SupabaseRepositoryPrimitives(Protocol):
    async def _request_rows(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> list[dict[str, Any]]: ...

    def _many(self, rows: list[dict[str, Any]], model: type[T]) -> list[T]: ...

    def _one(self, rows: list[dict[str, Any]], model: type[T]) -> T: ...


class SupabaseProvenanceDispositionMixin:
    async def list_provenance_dispositions(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
    ) -> list[ProvenanceDisposition]:
        client = cast(_SupabaseRepositoryPrimitives, self)
        rows = await client._request_rows(
            "GET",
            "/provenance_dispositions",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "document_id": f"eq.{document_id}",
                "order": "created_at.desc,id.desc",
            },
        )
        return client._many(rows, ProvenanceDisposition)

    async def create_provenance_disposition(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        accepted_proposal_id: UUID,
        request: CreateProvenanceDispositionRequest,
    ) -> ProvenanceDisposition:
        client = cast(_SupabaseRepositoryPrimitives, self)
        rows = await client._request_rows(
            "POST",
            "/provenance_dispositions",
            access_token=access_token,
            json={
                "project_id": str(project_id),
                "document_id": str(document_id),
                "accepted_proposal_id": str(accepted_proposal_id),
                "disposition": request.disposition.value,
                "draft_version": request.expected_draft_version,
                "superseding_proposal_id": (
                    None
                    if request.superseding_proposal_id is None
                    else str(request.superseding_proposal_id)
                ),
                "reason": request.reason,
            },
            prefer="return=representation",
        )
        return client._one(rows, ProvenanceDisposition)


class ProvenanceDispositionConflict(RuntimeError):
    pass


class ProvenanceDispositionValidationError(RuntimeError):
    pass


class ProvenanceDispositionService:
    def __init__(self, *, repository: ProvenanceDispositionRepository) -> None:
        self._repository = repository

    async def list(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
    ) -> list[ProvenanceDisposition]:
        draft = await self._repository.get_manuscript_draft(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        if draft is None:
            raise ProvenanceDispositionValidationError("Manuscript draft not found")
        return await self._repository.list_provenance_dispositions(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )

    async def create(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        proposal_id: UUID,
        request: CreateProvenanceDispositionRequest,
    ) -> ProvenanceDisposition:
        draft = await self._repository.get_manuscript_draft(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        if draft is None:
            raise ProvenanceDispositionValidationError("Manuscript draft not found")
        if draft.version != request.expected_draft_version:
            raise ProvenanceDispositionConflict(
                f"Draft version conflict: expected {request.expected_draft_version}, "
                f"current {draft.version}"
            )

        proposal = await self._repository.get_writing_proposal(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            proposal_id=proposal_id,
        )
        proposal = self._validate_grounded_accepted(proposal, label="Historical proposal")

        if request.disposition is ProvenanceDispositionKind.SUPERSEDED:
            superseding_proposal_id = request.superseding_proposal_id
            if superseding_proposal_id is None:
                raise ProvenanceDispositionValidationError(
                    "Superseded provenance requires a superseding proposal"
                )
            if superseding_proposal_id == proposal_id:
                raise ProvenanceDispositionValidationError("A proposal cannot supersede itself")
            replacement = await self._repository.get_writing_proposal(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                proposal_id=superseding_proposal_id,
            )
            replacement = self._validate_grounded_accepted(
                replacement,
                label="Superseding proposal",
            )
            if replacement.base_draft_version <= proposal.base_draft_version:
                raise ProvenanceDispositionValidationError(
                    "Superseding proposal must target a later manuscript draft"
                )
            historical_time = proposal.reviewed_at or proposal.updated_at or proposal.created_at
            replacement_time = (
                replacement.reviewed_at or replacement.updated_at or replacement.created_at
            )
            if replacement_time <= historical_time:
                raise ProvenanceDispositionValidationError(
                    "Superseding proposal must have been accepted after the historical proposal"
                )

        existing = await self._matching_existing(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            proposal_id=proposal_id,
            request=request,
        )
        if existing is not None:
            return existing

        try:
            return await self._repository.create_provenance_disposition(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                accepted_proposal_id=proposal_id,
                request=request,
            )
        except RepositoryError as exc:
            message = str(exc).lower()
            if "draft version" in message or "version conflict" in message:
                raise ProvenanceDispositionConflict(str(exc)) from exc
            if "duplicate" in message or "unique" in message:
                existing = await self._matching_existing(
                    access_token=access_token,
                    project_id=project_id,
                    document_id=document_id,
                    proposal_id=proposal_id,
                    request=request,
                )
                if existing is not None:
                    return existing
            raise

    async def _matching_existing(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        proposal_id: UUID,
        request: CreateProvenanceDispositionRequest,
    ) -> ProvenanceDisposition | None:
        existing = await self._repository.list_provenance_dispositions(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        for item in existing:
            if (
                item.accepted_proposal_id == proposal_id
                and item.draft_version == request.expected_draft_version
                and item.disposition is request.disposition
                and item.superseding_proposal_id == request.superseding_proposal_id
            ):
                return item
        return None

    @staticmethod
    def _validate_grounded_accepted(
        proposal: WritingProposal | None,
        *,
        label: str,
    ) -> WritingProposal:
        if proposal is None:
            raise ProvenanceDispositionValidationError(f"{label} not found")
        if proposal.status is not WritingProposalStatus.ACCEPTED:
            raise ProvenanceDispositionValidationError(f"{label} must be accepted")
        grounding = proposal.context_manifest.get("grounding")
        if not isinstance(grounding, dict) or not grounding.get("citations"):
            raise ProvenanceDispositionValidationError(f"{label} must be grounded")
        return proposal


def register_provenance_disposition_routes(
    *,
    app: FastAPI,
    repository: ProvenanceDispositionRepository,
    access_token_dependency: Callable[..., str],
) -> None:
    service = ProvenanceDispositionService(repository=repository)

    @app.get(
        "/api/projects/{project_id}/writing/documents/{document_id}/provenance-dispositions",
        response_model=list[ProvenanceDisposition],
    )
    async def list_provenance_dispositions(
        project_id: UUID,
        document_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> list[ProvenanceDisposition]:
        try:
            return await service.list(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
            )
        except ProvenanceDispositionValidationError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.post(
        "/api/projects/{project_id}/writing/documents/{document_id}/proposals/{proposal_id}/provenance-dispositions",
        response_model=ProvenanceDisposition,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_provenance_disposition(
        project_id: UUID,
        document_id: UUID,
        proposal_id: UUID,
        request: CreateProvenanceDispositionRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> ProvenanceDisposition:
        try:
            return await service.create(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                proposal_id=proposal_id,
                request=request,
            )
        except ProvenanceDispositionConflict as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except ProvenanceDispositionValidationError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
