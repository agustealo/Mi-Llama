from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Annotated, Any, Protocol, runtime_checkable
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from mi_llama.domain import ChatMessage, Role, SourceChunk
from mi_llama.providers.base import StructuredModelProvider
from mi_llama.providers.errors import ProviderError
from mi_llama.research_structure.models import (
    CitationCandidate,
    CitationStatus,
    ClaimEvidence,
)
from mi_llama.writing_structure.models import (
    WritingResearchLinkKind,
    WritingStructureNotFound,
)
from mi_llama.writing_studio.models import (
    WritingProposal,
    WritingProposalOperation,
)
from mi_llama.writing_studio.repository import WritingStudioRepository
from mi_llama.writing_studio.service import (
    DraftVersionConflict,
    WritingStudioService,
    WritingStudioValidationError,
)

MAX_GROUNDING_CITATIONS = 8
MAX_GROUNDING_CHARACTERS = 40_000
GROUNDING_MANIFEST_VERSION = 1


class CreateGroundedWritingProposalRequest(BaseModel):
    expected_draft_version: int = Field(ge=1)
    operation: WritingProposalOperation
    model: str = Field(min_length=1, max_length=200)
    selection_start: int = Field(ge=0)
    selection_end: int = Field(ge=1)
    prompt: str | None = Field(default=None, max_length=4000)
    citation_ids: list[UUID] = Field(min_length=1, max_length=MAX_GROUNDING_CITATIONS)

    @model_validator(mode="after")
    def validate_request(self) -> CreateGroundedWritingProposalRequest:
        if self.selection_end <= self.selection_start:
            raise ValueError("selection_end must be greater than selection_start")
        if len(set(self.citation_ids)) != len(self.citation_ids):
            raise ValueError("citation_ids must be unique")
        return self


@runtime_checkable
class GroundedProposalRepository(WritingStudioRepository, Protocol):
    async def get_citation_candidate(
        self,
        *,
        access_token: str,
        project_id: UUID,
        citation_id: UUID,
    ) -> CitationCandidate | None: ...

    async def get_claim_evidence(
        self,
        *,
        access_token: str,
        project_id: UUID,
        evidence_id: UUID,
    ) -> ClaimEvidence | None: ...


class FrozenGroundingItem(BaseModel):
    citation_id: UUID
    evidence_id: UUID
    claim_id: UUID
    source_id: UUID
    source_version_id: UUID
    chunk_id: UUID
    source_filename: str
    location: str | None = None
    stance: str
    note: str | None = None
    content: str
    content_sha256: str


class GroundedProposalService(WritingStudioService):
    def __init__(
        self,
        *,
        repository: GroundedProposalRepository,
        provider: StructuredModelProvider,
    ) -> None:
        super().__init__(repository=repository, provider=provider)
        self._grounded_repository = repository

    async def create_grounded_proposal(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        request: CreateGroundedWritingProposalRequest,
    ) -> WritingProposal:
        document = await self._require_document(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        draft = await self._grounded_repository.get_manuscript_draft(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        if draft is None:
            raise WritingStudioValidationError(
                "Save the manuscript draft before asking for an evidence-grounded edit"
            )
        if draft.version != request.expected_draft_version:
            raise DraftVersionConflict(
                "Draft version conflict: "
                f"expected {request.expected_draft_version}, current {draft.version}"
            )
        self._validate_selection(
            plain_text=draft.plain_text,
            selection_start=request.selection_start,
            selection_end=request.selection_end,
        )
        if draft.base_revision_id is None:
            raise WritingStudioValidationError(
                "Checkpoint the manuscript evidence before generating a grounded proposal"
            )

        original_text = draft.plain_text[request.selection_start : request.selection_end]
        before = draft.plain_text[max(0, request.selection_start - 800) : request.selection_start]
        after = draft.plain_text[request.selection_end : request.selection_end + 800]
        selection_hash = self._selection_hash(original_text)
        grounding = await self._resolve_grounding(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            revision_id=draft.base_revision_id,
            selection_start=request.selection_start,
            selection_end=request.selection_end,
            citation_ids=request.citation_ids,
        )

        context_manifest: dict[str, Any] = {
            "document_id": str(document_id),
            "document_title": document.title,
            "draft_version": draft.version,
            "base_revision_id": str(draft.base_revision_id),
            "selection_start": request.selection_start,
            "selection_end": request.selection_end,
            "selection_sha256": selection_hash,
            "before_context": before,
            "after_context": after,
            "grounding": {
                "version": GROUNDING_MANIFEST_VERSION,
                "citations": [item.model_dump(mode="json") for item in grounding],
            },
        }

        proposed_text = await self._generate_grounded_proposal(
            model=request.model,
            operation=request.operation,
            original_text=original_text,
            before_context=before,
            after_context=after,
            custom_prompt=request.prompt,
            grounding=grounding,
        )
        proposed_text = proposed_text.strip()
        if not proposed_text:
            raise WritingStudioValidationError("The model returned an empty writing proposal")
        if len(proposed_text) > 200_000:
            raise WritingStudioValidationError(
                "The writing proposal exceeds the maximum passage size"
            )

        return await self._grounded_repository.create_writing_proposal(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            base_draft_version=draft.version,
            base_revision_id=draft.base_revision_id,
            operation=request.operation,
            model=request.model,
            prompt=request.prompt,
            selection_start=request.selection_start,
            selection_end=request.selection_end,
            selection_hash=selection_hash,
            original_text=original_text,
            proposed_text=proposed_text,
            context_manifest=context_manifest,
        )

    async def _resolve_grounding(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        revision_id: UUID,
        selection_start: int,
        selection_end: int,
        citation_ids: list[UUID],
    ) -> list[FrozenGroundingItem]:
        links = await self._grounded_repository.list_writing_research_links(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        evidence_links = {
            link.entity_id
            for link in links
            if (
                link.kind is WritingResearchLinkKind.EVIDENCE
                and link.revision_id == revision_id
                and link.character_start == selection_start
                and link.character_end == selection_end
            )
        }
        if not evidence_links:
            raise WritingStudioValidationError(
                "No reviewed evidence is linked to this exact manuscript passage and revision"
            )

        frozen: list[FrozenGroundingItem] = []
        total_characters = 0
        for citation_id in citation_ids:
            citation = await self._grounded_repository.get_citation_candidate(
                access_token=access_token,
                project_id=project_id,
                citation_id=citation_id,
            )
            if citation is None:
                raise WritingStructureNotFound(str(citation_id))
            if citation.status is CitationStatus.REJECTED:
                raise WritingStudioValidationError(
                    "Rejected citations cannot ground writing proposals"
                )
            if citation.evidence_id not in evidence_links:
                raise WritingStudioValidationError(
                    "A grounding citation is not linked to this exact manuscript passage"
                )

            evidence = await self._grounded_repository.get_claim_evidence(
                access_token=access_token,
                project_id=project_id,
                evidence_id=citation.evidence_id,
            )
            if evidence is None or evidence.id != citation.evidence_id:
                raise WritingStructureNotFound(str(citation.evidence_id))
            if evidence.claim_id != citation.claim_id:
                raise WritingStudioValidationError(
                    "Citation and evidence claim provenance do not match"
                )

            source = await self._grounded_repository.get_source(
                access_token=access_token,
                source_id=evidence.source_id,
            )
            if source is None or source.project_id != project_id:
                raise WritingStructureNotFound(str(evidence.source_id))
            chunks = await self._grounded_repository.get_source_chunks(
                access_token=access_token,
                source_version_id=evidence.source_version_id,
            )
            chunk = self._find_exact_chunk(chunks=chunks, evidence=evidence, project_id=project_id)
            total_characters += len(chunk.content)
            if total_characters > MAX_GROUNDING_CHARACTERS:
                raise WritingStudioValidationError(
                    f"Grounding evidence exceeds the {MAX_GROUNDING_CHARACTERS} character limit"
                )

            frozen.append(
                FrozenGroundingItem(
                    citation_id=citation.id,
                    evidence_id=evidence.id,
                    claim_id=evidence.claim_id,
                    source_id=evidence.source_id,
                    source_version_id=evidence.source_version_id,
                    chunk_id=evidence.chunk_id,
                    source_filename=source.filename,
                    location=chunk.location,
                    stance=evidence.stance.value,
                    note=evidence.note,
                    content=chunk.content,
                    content_sha256=hashlib.sha256(chunk.content.encode("utf-8")).hexdigest(),
                )
            )
        return frozen

    @staticmethod
    def _find_exact_chunk(
        *,
        chunks: list[SourceChunk],
        evidence: ClaimEvidence,
        project_id: UUID,
    ) -> SourceChunk:
        for chunk in chunks:
            if (
                chunk.id == evidence.chunk_id
                and chunk.source_id == evidence.source_id
                and chunk.source_version_id == evidence.source_version_id
                and chunk.project_id == project_id
            ):
                return chunk
        raise WritingStudioValidationError(
            "The canonical source chunk for reviewed evidence is no longer available"
        )

    async def _generate_grounded_proposal(
        self,
        *,
        model: str,
        operation: WritingProposalOperation,
        original_text: str,
        before_context: str,
        after_context: str,
        custom_prompt: str | None,
        grounding: list[FrozenGroundingItem],
    ) -> str:
        operation_instruction = {
            WritingProposalOperation.REWRITE: (
                "Rewrite the selected passage while preserving its meaning and respecting the reviewed evidence."
            ),
            WritingProposalOperation.IMPROVE: (
                "Improve clarity, precision, flow, and readability while grounding source-dependent claims in the reviewed evidence."
            ),
            WritingProposalOperation.EXPAND: (
                "Expand the selected passage only where the reviewed evidence supports useful additions."
            ),
            WritingProposalOperation.CONDENSE: (
                "Make the selected passage materially shorter while preserving the argument and evidence-supported facts."
            ),
            WritingProposalOperation.CONTINUE: (
                "Continue the selected passage naturally using only source-dependent facts supported by the reviewed evidence."
            ),
            WritingProposalOperation.CUSTOM: (
                "Follow the writer's instruction while treating the reviewed evidence as the factual boundary."
            ),
        }[operation]
        user_instruction = custom_prompt.strip() if custom_prompt else "No additional instruction."
        evidence_text = format_grounding_for_model(grounding)
        payload = await self._provider.chat_json(
            model=model,
            messages=[
                ChatMessage(
                    role=Role.SYSTEM,
                    content=(
                        "You are Mi-Llama's evidence-grounded manuscript collaborator. Produce only a replacement for the selected passage. "
                        "The reviewed evidence packet is canonical for this request. Respect each source's supports, contradicts, or context stance. "
                        "Do not convert contextual or contradictory evidence into support. Never invent sources, citations, quotations, statistics, names, dates, or factual claims outside the supplied manuscript context and reviewed evidence. "
                        "Do not emit citation markup unless it already exists in the selected passage; citation insertion remains a separate writer-reviewed authority."
                    ),
                ),
                ChatMessage(
                    role=Role.USER,
                    content=(
                        f"Operation: {operation.value}\n"
                        f"Instruction: {operation_instruction}\n"
                        f"Writer instruction: {user_instruction}\n\n"
                        f"Context before:\n{before_context}\n\n"
                        f"Selected passage:\n{original_text}\n\n"
                        f"Context after:\n{after_context}\n\n"
                        f"Reviewed evidence packet:\n{evidence_text}"
                    ),
                ),
            ],
            schema={
                "type": "object",
                "properties": {"replacement": {"type": "string"}},
                "required": ["replacement"],
                "additionalProperties": False,
            },
        )
        replacement = payload.get("replacement")
        if not isinstance(replacement, str):
            raise WritingStudioValidationError("The model returned an invalid writing proposal")
        return replacement


def format_grounding_for_model(items: list[FrozenGroundingItem]) -> str:
    blocks: list[str] = []
    for index, item in enumerate(items, start=1):
        location = item.location or "unspecified location"
        note = item.note or "None"
        blocks.append(
            "\n".join(
                [
                    f"Evidence {index}",
                    f"Source: {item.source_filename}",
                    f"Location: {location}",
                    f"Stance: {item.stance}",
                    f"Reviewer note: {note}",
                    f"Source passage: {item.content}",
                ]
            )
        )
    return "\n\n".join(blocks)


def grounding_prompt_from_manifest(context_manifest: dict[str, Any]) -> str:
    raw = context_manifest.get("grounding")
    if not isinstance(raw, dict) or raw.get("version") != GROUNDING_MANIFEST_VERSION:
        return ""
    citations = raw.get("citations")
    if not isinstance(citations, list) or not citations:
        return ""
    items: list[FrozenGroundingItem] = []
    for item in citations:
        if not isinstance(item, dict):
            raise WritingStudioValidationError("Grounding manifest contains invalid evidence")
        parsed = FrozenGroundingItem.model_validate(item)
        actual_hash = hashlib.sha256(parsed.content.encode("utf-8")).hexdigest()
        if actual_hash != parsed.content_sha256:
            raise WritingStudioValidationError("Grounding manifest evidence hash does not match")
        items.append(parsed)
    return format_grounding_for_model(items)


def register_grounded_proposal_routes(
    *,
    app: FastAPI,
    repository: GroundedProposalRepository,
    provider: StructuredModelProvider,
    access_token_dependency: Callable[..., str],
) -> None:
    service = GroundedProposalService(repository=repository, provider=provider)

    @app.post(
        "/api/projects/{project_id}/writing/documents/{document_id}/grounded-proposals",
        response_model=WritingProposal,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_grounded_writing_proposal(
        project_id: UUID,
        document_id: UUID,
        request: CreateGroundedWritingProposalRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> WritingProposal:
        try:
            return await service.create_grounded_proposal(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                request=request,
            )
        except WritingStructureNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Manuscript evidence or source not found",
            ) from exc
        except DraftVersionConflict as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except WritingStudioValidationError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except ProviderError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
