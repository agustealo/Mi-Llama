from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Protocol, Self, runtime_checkable
from uuid import UUID

from citeproc import (
    Citation,
    CitationItem,
    CitationStylesBibliography,
    CitationStylesStyle,
    formatter,
)
from citeproc.source.json import CiteProcJSON
from citeproc_styles import get_style_filepath
from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from mi_llama.repositories import RepositoryError
from mi_llama.research_structure.models import CitationCandidate, ClaimEvidence
from mi_llama.writing_evidence import SupabaseWritingEvidenceRepository, WritingEvidenceRepository
from mi_llama.writing_structure.models import ManuscriptRevision, WritingResearchLink
from mi_llama.writing_studio.models import ManuscriptDraft


class CitationProfile(StrEnum):
    APA_7 = "apa-7"
    MLA_9 = "mla-9"
    CHICAGO_AUTHOR_DATE = "chicago-author-date"


_STYLE_FILES = {
    CitationProfile.APA_7: "apa",
    CitationProfile.MLA_9: "modern-language-association",
    CitationProfile.CHICAGO_AUTHOR_DATE: "chicago-author-date",
}


class CitationAuthor(BaseModel):
    family: str = Field(min_length=1, max_length=200)
    given: str | None = Field(default=None, max_length=200)


class SaveSourceCitationMetadataRequest(BaseModel):
    expected_version: int | None = Field(default=None, ge=1)
    item_type: Literal[
        "article-journal",
        "article-magazine",
        "article-newspaper",
        "book",
        "chapter",
        "manuscript",
        "paper-conference",
        "report",
        "thesis",
        "webpage",
    ]
    title: str = Field(min_length=1, max_length=1000)
    authors: list[CitationAuthor] = Field(default_factory=list, max_length=100)
    issued_year: int | None = Field(default=None, ge=1, le=9999)
    issued_month: int | None = Field(default=None, ge=1, le=12)
    issued_day: int | None = Field(default=None, ge=1, le=31)
    container_title: str | None = Field(default=None, max_length=1000)
    publisher: str | None = Field(default=None, max_length=500)
    publisher_place: str | None = Field(default=None, max_length=500)
    volume: str | None = Field(default=None, max_length=100)
    issue: str | None = Field(default=None, max_length=100)
    page: str | None = Field(default=None, max_length=100)
    edition: str | None = Field(default=None, max_length=100)
    doi: str | None = Field(default=None, max_length=500)
    url: str | None = Field(default=None, max_length=2000)
    isbn: str | None = Field(default=None, max_length=100)
    issn: str | None = Field(default=None, max_length=100)
    language: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_date_parts(self) -> Self:
        if self.issued_day is not None and self.issued_month is None:
            raise ValueError("issued_day requires issued_month")
        if self.issued_month is not None and self.issued_year is None:
            raise ValueError("issued_month requires issued_year")
        return self

    def to_csl_json(self, *, source_id: UUID) -> dict[str, Any]:
        item: dict[str, Any] = {
            "id": str(source_id),
            "type": self.item_type,
            "title": self.title.strip(),
        }
        if self.authors:
            item["author"] = [
                {
                    "family": author.family.strip(),
                    **(
                        {"given": author.given.strip()}
                        if author.given and author.given.strip()
                        else {}
                    ),
                }
                for author in self.authors
            ]
        if self.issued_year is not None:
            parts = [self.issued_year]
            if self.issued_month is not None:
                parts.append(self.issued_month)
            if self.issued_day is not None:
                parts.append(self.issued_day)
            item["issued"] = {"date-parts": [parts]}
        optional = {
            "container-title": self.container_title,
            "publisher": self.publisher,
            "publisher-place": self.publisher_place,
            "volume": self.volume,
            "issue": self.issue,
            "page": self.page,
            "edition": self.edition,
            "DOI": self.doi,
            "URL": self.url,
            "ISBN": self.isbn,
            "ISSN": self.issn,
            "language": self.language,
        }
        for key, value in optional.items():
            if value is not None and value.strip():
                item[key] = value.strip()
        return item


class SourceCitationMetadata(BaseModel):
    source_id: UUID
    project_id: UUID
    created_by: UUID
    updated_by: UUID
    version: int = Field(ge=1)
    csl: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class CitationPreviewRequest(BaseModel):
    style: CitationProfile


class CitationPreview(BaseModel):
    citation_id: UUID
    source_id: UUID
    metadata_version: int
    style: CitationProfile
    in_text: str
    bibliography: str


class InsertCitationRequest(BaseModel):
    insertion_id: UUID
    expected_draft_version: int = Field(ge=1)
    metadata_version: int = Field(ge=1)
    style: CitationProfile


class CitationInsertion(BaseModel):
    id: UUID
    project_id: UUID
    document_id: UUID
    citation_id: UUID
    source_id: UUID
    metadata_version: int
    style: CitationProfile
    rendered_citation: str
    rendered_bibliography: str
    revision_id: UUID
    character_start: int = Field(ge=0)
    character_end: int = Field(ge=1)
    created_by: UUID
    created_at: datetime


class CitationContext(BaseModel):
    citation: CitationCandidate
    evidence: ClaimEvidence
    metadata: SourceCitationMetadata | None = None
    insertion: CitationInsertion | None = None


class CitationInsertionResult(BaseModel):
    draft: ManuscriptDraft
    revision: ManuscriptRevision
    citation: CitationCandidate
    citation_link: WritingResearchLink
    insertion: CitationInsertion


class CitationAuthorityError(RuntimeError):
    pass


class CitationAuthorityNotFound(CitationAuthorityError):
    pass


class CitationAuthorityConflict(CitationAuthorityError):
    pass


class CitationRenderError(CitationAuthorityError):
    pass


@runtime_checkable
class CitationAuthorityRepository(WritingEvidenceRepository, Protocol):
    async def get_citation_candidate(
        self, *, access_token: str, project_id: UUID, citation_id: UUID
    ) -> CitationCandidate | None: ...

    async def get_claim_evidence(
        self, *, access_token: str, project_id: UUID, evidence_id: UUID
    ) -> ClaimEvidence | None: ...

    async def get_source_citation_metadata(
        self, *, access_token: str, project_id: UUID, source_id: UUID
    ) -> SourceCitationMetadata | None: ...

    async def get_citation_insertion(
        self, *, access_token: str, project_id: UUID, citation_id: UUID
    ) -> CitationInsertion | None: ...

    async def save_source_citation_metadata(
        self,
        *,
        access_token: str,
        project_id: UUID,
        source_id: UUID,
        expected_version: int | None,
        csl: dict[str, Any],
    ) -> SourceCitationMetadata: ...

    async def insert_writing_citation(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        citation_id: UUID,
        request: InsertCitationRequest,
        rendered: CitationPreview,
    ) -> CitationInsertionResult: ...


class SupabaseCitationAuthorityRepository(SupabaseWritingEvidenceRepository):
    async def get_citation_insertion(
        self, *, access_token: str, project_id: UUID, citation_id: UUID
    ) -> CitationInsertion | None:
        rows = await self._request_rows(
            "GET",
            "/citation_insertions",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "citation_id": f"eq.{citation_id}",
                "limit": "1",
            },
        )
        return None if not rows else self._one(rows, CitationInsertion)

    async def get_source_citation_metadata(
        self, *, access_token: str, project_id: UUID, source_id: UUID
    ) -> SourceCitationMetadata | None:
        rows = await self._request_rows(
            "GET",
            "/source_citation_metadata",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "source_id": f"eq.{source_id}",
                "limit": "1",
            },
        )
        return None if not rows else self._one(rows, SourceCitationMetadata)

    async def save_source_citation_metadata(
        self,
        *,
        access_token: str,
        project_id: UUID,
        source_id: UUID,
        expected_version: int | None,
        csl: dict[str, Any],
    ) -> SourceCitationMetadata:
        rows = await self._request_rows(
            "POST",
            "/rpc/save_source_citation_metadata",
            access_token=access_token,
            json={
                "p_project_id": str(project_id),
                "p_source_id": str(source_id),
                "p_expected_version": expected_version,
                "p_csl": csl,
            },
        )
        return self._one(rows, SourceCitationMetadata)

    async def insert_writing_citation(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        citation_id: UUID,
        request: InsertCitationRequest,
        rendered: CitationPreview,
    ) -> CitationInsertionResult:
        rows = await self._request_rows(
            "POST",
            "/rpc/insert_writing_citation",
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
            },
        )
        return self._one(rows, CitationInsertionResult)


def render_citation(
    *, citation_id: UUID, metadata: SourceCitationMetadata, style: CitationProfile
) -> CitationPreview:
    item = dict(metadata.csl)
    item["id"] = str(metadata.source_id)
    missing: list[str] = []

    try:
        source = CiteProcJSON([item])
        csl_style = CitationStylesStyle(get_style_filepath(_STYLE_FILES[style]), validate=False)
        bibliography = CitationStylesBibliography(csl_style, source, formatter.plain)
        citation = Citation([CitationItem(str(metadata.source_id))])
        bibliography.register(citation)

        def warn(citation_item: Any) -> None:
            missing.append(str(citation_item.key))

        in_text = str(bibliography.cite(citation, warn)).strip()
        entries = bibliography.bibliography()
        bibliography_text = str(entries[0]).strip() if entries else ""
    except Exception as exc:  # citeproc exposes multiple parser/render error classes
        raise CitationRenderError(f"Citation renderer failed: {exc}") from exc

    if missing or not in_text or not bibliography_text:
        raise CitationRenderError("Citation metadata could not be rendered by the selected style")

    return CitationPreview(
        citation_id=citation_id,
        source_id=metadata.source_id,
        metadata_version=metadata.version,
        style=style,
        in_text=in_text,
        bibliography=bibliography_text,
    )


class CitationAuthorityService:
    def __init__(self, *, repository: CitationAuthorityRepository) -> None:
        self._repository = repository

    async def save_metadata(
        self,
        *,
        access_token: str,
        project_id: UUID,
        source_id: UUID,
        request: SaveSourceCitationMetadataRequest,
    ) -> SourceCitationMetadata:
        return await self._repository.save_source_citation_metadata(
            access_token=access_token,
            project_id=project_id,
            source_id=source_id,
            expected_version=request.expected_version,
            csl=request.to_csl_json(source_id=source_id),
        )

    async def preview(
        self,
        *,
        access_token: str,
        project_id: UUID,
        citation_id: UUID,
        style: CitationProfile,
    ) -> CitationPreview:
        citation, _evidence, metadata = await self._context(
            access_token=access_token,
            project_id=project_id,
            citation_id=citation_id,
        )
        return render_citation(citation_id=citation.id, metadata=metadata, style=style)

    async def insert(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        citation_id: UUID,
        request: InsertCitationRequest,
    ) -> CitationInsertionResult:
        citation, _evidence, metadata = await self._context(
            access_token=access_token,
            project_id=project_id,
            citation_id=citation_id,
        )
        if metadata.version != request.metadata_version:
            raise CitationAuthorityConflict(
                "Citation metadata changed; refresh the preview before insertion"
            )
        rendered = render_citation(citation_id=citation.id, metadata=metadata, style=request.style)
        return await self._repository.insert_writing_citation(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            citation_id=citation_id,
            request=request,
            rendered=rendered,
        )

    async def context(
        self, *, access_token: str, project_id: UUID, citation_id: UUID
    ) -> CitationContext:
        citation = await self._repository.get_citation_candidate(
            access_token=access_token, project_id=project_id, citation_id=citation_id
        )
        if citation is None:
            raise CitationAuthorityNotFound("Citation candidate not found")
        evidence = await self._repository.get_claim_evidence(
            access_token=access_token, project_id=project_id, evidence_id=citation.evidence_id
        )
        if evidence is None:
            raise CitationAuthorityNotFound("Citation evidence not found")
        metadata = await self._repository.get_source_citation_metadata(
            access_token=access_token, project_id=project_id, source_id=evidence.source_id
        )
        insertion = await self._repository.get_citation_insertion(
            access_token=access_token, project_id=project_id, citation_id=citation_id
        )
        return CitationContext(
            citation=citation, evidence=evidence, metadata=metadata, insertion=insertion
        )

    async def _context(
        self, *, access_token: str, project_id: UUID, citation_id: UUID
    ) -> tuple[CitationCandidate, ClaimEvidence, SourceCitationMetadata]:
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
        return citation, evidence, metadata


def _map_repository_error(exc: RepositoryError) -> CitationAuthorityError | None:
    message = str(exc)
    lowered = message.lower()
    if any(marker in lowered for marker in ("stale", "version", "draft changed", "checkpoint")):
        return CitationAuthorityConflict(message)
    if "not found" in lowered or "required" in lowered:
        return CitationAuthorityNotFound(message)
    return None


def register_citation_authority_routes(
    *,
    app: FastAPI,
    repository: CitationAuthorityRepository,
    access_token_dependency: Callable[..., str],
) -> None:
    service = CitationAuthorityService(repository=repository)

    @app.get(
        "/api/projects/{project_id}/sources/{source_id}/citation-metadata",
        response_model=SourceCitationMetadata | None,
    )
    async def get_citation_metadata(
        project_id: UUID,
        source_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> SourceCitationMetadata | None:
        return await repository.get_source_citation_metadata(
            access_token=access_token,
            project_id=project_id,
            source_id=source_id,
        )

    @app.put(
        "/api/projects/{project_id}/sources/{source_id}/citation-metadata",
        response_model=SourceCitationMetadata,
    )
    async def save_citation_metadata(
        project_id: UUID,
        source_id: UUID,
        request: SaveSourceCitationMetadataRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> SourceCitationMetadata:
        try:
            return await service.save_metadata(
                access_token=access_token,
                project_id=project_id,
                source_id=source_id,
                request=request,
            )
        except RepositoryError as exc:
            mapped = _map_repository_error(exc)
            if isinstance(mapped, CitationAuthorityConflict):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail=str(mapped)
                ) from exc
            if isinstance(mapped, CitationAuthorityNotFound):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail=str(mapped)
                ) from exc
            raise

    @app.get(
        "/api/projects/{project_id}/research/citations/{citation_id}/context",
        response_model=CitationContext,
    )
    async def get_citation_context(
        project_id: UUID,
        citation_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> CitationContext:
        try:
            return await service.context(
                access_token=access_token, project_id=project_id, citation_id=citation_id
            )
        except CitationAuthorityNotFound as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.post(
        "/api/projects/{project_id}/research/citations/{citation_id}/preview",
        response_model=CitationPreview,
    )
    async def preview_citation(
        project_id: UUID,
        citation_id: UUID,
        request: CitationPreviewRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> CitationPreview:
        try:
            return await service.preview(
                access_token=access_token,
                project_id=project_id,
                citation_id=citation_id,
                style=request.style,
            )
        except CitationAuthorityNotFound as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except CitationRenderError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc

    @app.post(
        "/api/projects/{project_id}/writing/documents/{document_id}/citations/{citation_id}/insert",
        response_model=CitationInsertionResult,
        status_code=status.HTTP_201_CREATED,
    )
    async def insert_citation(
        project_id: UUID,
        document_id: UUID,
        citation_id: UUID,
        request: InsertCitationRequest,
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
        except CitationAuthorityNotFound as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except CitationAuthorityConflict as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except CitationRenderError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        except RepositoryError as exc:
            mapped = _map_repository_error(exc)
            if isinstance(mapped, CitationAuthorityConflict):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail=str(mapped)
                ) from exc
            if isinstance(mapped, CitationAuthorityNotFound):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail=str(mapped)
                ) from exc
            raise
