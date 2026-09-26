from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Annotated, Any, Protocol, runtime_checkable
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from mi_llama.citation_authority import (
    CitationAuthorityConflict,
    CitationAuthorityNotFound,
    CitationAuthorityRepository,
    CitationInsertionResult,
    CitationPreview,
    CitationPreviewRequest,
    CitationProfile,
    CitationRenderError,
    SupabaseCitationAuthorityRepository,
    render_citation,
)
from mi_llama.editor_state import EditorStateError, validate_editor_state
from mi_llama.repositories import RepositoryError
from mi_llama.writing_structure.models import (
    ManuscriptRevision,
    WritingResearchLink,
    WritingResearchLinkKind,
)
from mi_llama.writing_studio.models import ManuscriptDraft


class StructuredCitationInsertionRequest(BaseModel):
    insertion_id: UUID
    expected_draft_version: int = Field(ge=1)
    metadata_version: int = Field(ge=1)
    style: CitationProfile
    editor_state: dict[str, Any]
    plain_text: str = Field(max_length=2_000_000)

    @model_validator(mode="after")
    def validate_document_projection(self) -> StructuredCitationInsertionRequest:
        try:
            validate_editor_state(self.editor_state, self.plain_text)
        except EditorStateError as exc:
            raise ValueError(str(exc)) from exc
        return self


class CitationInsertionPlan(BaseModel):
    citation_id: UUID
    source_id: UUID
    metadata_version: int
    style: CitationProfile
    expected_draft_version: int = Field(ge=1)
    base_revision_id: UUID
    evidence_revision_id: UUID
    insertion_position: int = Field(ge=0)
    fragment: str = Field(min_length=1, max_length=1001)
    citation_start: int = Field(ge=0)
    citation_end: int = Field(ge=1)
    rendered_citation: str
    rendered_bibliography: str
    current_plain_text_sha256: str = Field(min_length=64, max_length=64)
    resulting_plain_text_sha256: str = Field(min_length=64, max_length=64)


@runtime_checkable
class StructuredCitationRepository(CitationAuthorityRepository, Protocol):
    async def get_manuscript_draft(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
    ) -> ManuscriptDraft | None: ...

    async def list_writing_research_links(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID | None = None,
    ) -> list[WritingResearchLink]: ...

    async def get_manuscript_revision(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        revision_id: UUID,
    ) -> ManuscriptRevision | None: ...

    async def insert_structured_writing_citation(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        citation_id: UUID,
        request: StructuredCitationInsertionRequest,
        rendered: CitationPreview,
    ) -> CitationInsertionResult: ...


class SupabaseStructuredCitationRepository(SupabaseCitationAuthorityRepository):
    async def insert_structured_writing_citation(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        citation_id: UUID,
        request: StructuredCitationInsertionRequest,
        rendered: CitationPreview,
    ) -> CitationInsertionResult:
        rows = await self._request_rows(
            "POST",
            "/rpc/insert_writing_citation_structured",
            access_token=access_token,
            json={
                "p_project_id": str(project_id),
                "p_document_id": str(document_id),
                "p_citation_id": str(citation_id),
                "p_insertion_id": str(request.insertion_id),
                "p_expected_draft_version": request.expected_draft_version,
                "p_metadata_version": request.metadata_version,
                "p_style": request.style.value,
                "p_rendered_citation": rendered.in_text,
                "p_rendered_bibliography": rendered.bibliography,
                "p_editor_state": request.editor_state,
                "p_plain_text": request.plain_text,
            },
        )
        return self._one(rows, CitationInsertionResult)


class StructuredCitationService:
    def __init__(self, *, repository: StructuredCitationRepository) -> None:
        self._repository = repository

    async def plan(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        citation_id: UUID,
        style: CitationProfile,
    ) -> CitationInsertionPlan:
        plan, _next_content, _rendered = await self._prepare(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            citation_id=citation_id,
            style=style,
        )
        return plan

    async def insert(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        citation_id: UUID,
        request: StructuredCitationInsertionRequest,
    ) -> CitationInsertionResult:
        plan, next_content, rendered = await self._prepare(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            citation_id=citation_id,
            style=request.style,
        )
        if plan.expected_draft_version != request.expected_draft_version:
            raise CitationAuthorityConflict("Manuscript draft version changed after the citation plan")
        if plan.metadata_version != request.metadata_version:
            raise CitationAuthorityConflict("Citation metadata changed; refresh the citation plan")
        if request.plain_text != next_content:
            raise CitationAuthorityConflict(
                "Structured citation document does not match the canonical citation insertion"
            )
        try:
            validate_editor_state(request.editor_state, request.plain_text)
        except EditorStateError as exc:
            raise CitationAuthorityConflict(str(exc)) from exc

        return await self._repository.insert_structured_writing_citation(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            citation_id=citation_id,
            request=request,
            rendered=rendered,
        )

    async def _prepare(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        citation_id: UUID,
        style: CitationProfile,
    ) -> tuple[CitationInsertionPlan, str, CitationPreview]:
        citation = await self._repository.get_citation_candidate(
            access_token=access_token,
            project_id=project_id,
            citation_id=citation_id,
        )
        if citation is None:
            raise CitationAuthorityNotFound("Citation candidate not found")

        evidence = await self._repository.get_claim_evidence(
            access_token=access_token,
            project_id=project_id,
            evidence_id=citation.evidence_id,
        )
        if evidence is None:
            raise CitationAuthorityNotFound("Citation evidence not found")

        metadata = await self._repository.get_source_citation_metadata(
            access_token=access_token,
            project_id=project_id,
            source_id=evidence.source_id,
        )
        if metadata is None:
            raise CitationAuthorityNotFound("Source citation metadata is required")
        rendered = render_citation(citation_id=citation.id, metadata=metadata, style=style)

        draft = await self._repository.get_manuscript_draft(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        if draft is None:
            raise CitationAuthorityNotFound("Manuscript draft not found")

        links = await self._repository.list_writing_research_links(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        evidence_links = [
            link
            for link in links
            if link.kind == WritingResearchLinkKind.EVIDENCE
            and link.entity_id == evidence.id
            and link.revision_id is not None
            and link.character_start is not None
            and link.character_end is not None
        ]
        if not evidence_links:
            raise CitationAuthorityNotFound("Citation evidence is not linked to this manuscript")

        evidence_link = max(evidence_links, key=lambda link: link.created_at)
        assert evidence_link.revision_id is not None
        assert evidence_link.character_start is not None
        assert evidence_link.character_end is not None

        revision = await self._repository.get_manuscript_revision(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            revision_id=evidence_link.revision_id,
        )
        if revision is None:
            raise CitationAuthorityNotFound("Citation evidence revision not found")
        if draft.base_revision_id != revision.id or draft.plain_text != revision.content:
            raise CitationAuthorityConflict(
                "Manuscript draft changed after the evidence checkpoint"
            )

        plan, next_content = build_citation_insertion_plan(
            citation_id=citation.id,
            source_id=evidence.source_id,
            metadata_version=metadata.version,
            style=style,
            draft=draft,
            revision=revision,
            evidence_link=evidence_link,
            rendered=rendered,
        )
        return plan, next_content, rendered


def build_citation_insertion_plan(
    *,
    citation_id: UUID,
    source_id: UUID,
    metadata_version: int,
    style: CitationProfile,
    draft: ManuscriptDraft,
    revision: ManuscriptRevision,
    evidence_link: WritingResearchLink,
    rendered: CitationPreview,
) -> tuple[CitationInsertionPlan, str]:
    start = evidence_link.character_start
    end = evidence_link.character_end
    if start is None or end is None or evidence_link.revision_id is None:
        raise CitationAuthorityConflict("Citation evidence link is missing a stable manuscript range")
    if start < 0 or end <= start or end > len(revision.content):
        raise CitationAuthorityConflict("Citation evidence range is outside the manuscript revision")

    insertion_position = end
    if insertion_position > start and revision.content[insertion_position - 1] in ".!?":
        insertion_position -= 1

    citation_text = rendered.in_text.strip()
    if not citation_text:
        raise CitationRenderError("Rendered citation is empty")
    if insertion_position == 0 or revision.content[insertion_position - 1].isspace():
        fragment = citation_text
    else:
        fragment = f" {citation_text}"

    citation_start = insertion_position + len(fragment) - len(citation_text)
    citation_end = citation_start + len(citation_text)
    next_content = (
        revision.content[:insertion_position]
        + fragment
        + revision.content[insertion_position:]
    )
    if len(next_content) > 2_000_000:
        raise CitationAuthorityConflict("Manuscript draft exceeds maximum size")

    return (
        CitationInsertionPlan(
            citation_id=citation_id,
            source_id=source_id,
            metadata_version=metadata_version,
            style=style,
            expected_draft_version=draft.version,
            base_revision_id=revision.id,
            evidence_revision_id=revision.id,
            insertion_position=insertion_position,
            fragment=fragment,
            citation_start=citation_start,
            citation_end=citation_end,
            rendered_citation=citation_text,
            rendered_bibliography=rendered.bibliography,
            current_plain_text_sha256=_sha256(revision.content),
            resulting_plain_text_sha256=_sha256(next_content),
        ),
        next_content,
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _map_structured_citation_error(
    exc: RepositoryError,
) -> CitationAuthorityConflict | CitationAuthorityNotFound | None:
    message = str(exc)
    lowered = message.lower()
    if any(
        marker in lowered
        for marker in (
            "stale",
            "version",
            "draft changed",
            "checkpoint",
            "canonical insertion",
            "structured citation",
        )
    ):
        return CitationAuthorityConflict(message)
    if "not found" in lowered or "required" in lowered:
        return CitationAuthorityNotFound(message)
    return None


def _http_error(exc: Exception) -> HTTPException | None:
    if isinstance(exc, CitationAuthorityNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, CitationAuthorityConflict):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, CitationRenderError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    if isinstance(exc, RepositoryError):
        mapped = _map_structured_citation_error(exc)
        if mapped is not None:
            return _http_error(mapped)
    return None


def register_structured_citation_routes(
    *,
    app: FastAPI,
    repository: StructuredCitationRepository,
    access_token_dependency: Callable[..., str],
) -> None:
    service = StructuredCitationService(repository=repository)

    @app.post(
        "/api/projects/{project_id}/writing/documents/{document_id}/citations/{citation_id}/plan",
        response_model=CitationInsertionPlan,
    )
    async def plan_structured_citation(
        project_id: UUID,
        document_id: UUID,
        citation_id: UUID,
        request: CitationPreviewRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> CitationInsertionPlan:
        try:
            return await service.plan(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                citation_id=citation_id,
                style=request.style,
            )
        except (
            CitationAuthorityNotFound,
            CitationAuthorityConflict,
            CitationRenderError,
            RepositoryError,
        ) as exc:
            mapped = _http_error(exc)
            if mapped is None:
                raise
            raise mapped from exc

    @app.post(
        "/api/projects/{project_id}/writing/documents/{document_id}/citations/{citation_id}/insert-structured",
        response_model=CitationInsertionResult,
        status_code=status.HTTP_201_CREATED,
    )
    async def insert_structured_citation(
        project_id: UUID,
        document_id: UUID,
        citation_id: UUID,
        request: StructuredCitationInsertionRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> CitationInsertionResult:
        try:
            return await service.insert(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                citation_id=citation_id,
                request=request,
            )
        except (
            CitationAuthorityNotFound,
            CitationAuthorityConflict,
            CitationRenderError,
            RepositoryError,
        ) as exc:
            mapped = _http_error(exc)
            if mapped is None:
                raise
            raise mapped from exc
