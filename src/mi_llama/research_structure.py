from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Protocol, runtime_checkable
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from mi_llama.domain import LearningEvent, ResearchResponse, SourceChunk
from mi_llama.repositories import SupabaseRepository
from mi_llama.research import AuthorizedResearchService, ResearchError


class ResearchQuestionStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    PARKED = "parked"


class ClaimStatus(StrEnum):
    NEEDS_EVIDENCE = "needs_evidence"
    SUPPORTED = "supported"
    DISPUTED = "disputed"


class EvidenceStance(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CONTEXT = "context"


class CitationStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ResearchNoteKind(StrEnum):
    NOTE = "note"
    QUOTE = "quote"
    IDEA = "idea"
    SUMMARY = "summary"


class ResearchGapKind(StrEnum):
    OPEN_QUESTION = "open_question"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    DISPUTED_CLAIM = "disputed_claim"
    PENDING_CITATION = "pending_citation"


class ResearchQuestion(BaseModel):
    id: UUID
    project_id: UUID
    created_by: UUID
    question: str
    status: ResearchQuestionStatus
    priority: int = Field(ge=1, le=5)
    resolution: str | None = None
    created_at: datetime
    updated_at: datetime


class CreateResearchQuestionRequest(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    priority: int = Field(default=3, ge=1, le=5)


class UpdateResearchQuestionRequest(BaseModel):
    question: str | None = Field(default=None, min_length=3, max_length=4000)
    status: ResearchQuestionStatus | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    resolution: str | None = Field(default=None, max_length=8000)


class ResearchClaim(BaseModel):
    id: UUID
    project_id: UUID
    created_by: UUID
    statement: str
    status: ClaimStatus
    created_at: datetime
    updated_at: datetime


class CreateClaimRequest(BaseModel):
    statement: str = Field(min_length=3, max_length=8000)


class ResearchNote(BaseModel):
    id: UUID
    project_id: UUID
    created_by: UUID
    question_id: UUID | None = None
    source_chunk_id: UUID | None = None
    kind: ResearchNoteKind
    title: str | None = None
    body: str
    created_at: datetime
    updated_at: datetime


class CreateResearchNoteRequest(BaseModel):
    question_id: UUID | None = None
    source_chunk_id: UUID | None = None
    kind: ResearchNoteKind = ResearchNoteKind.NOTE
    title: str | None = Field(default=None, max_length=240)
    body: str = Field(min_length=1, max_length=40_000)


class ClaimEvidence(BaseModel):
    id: UUID
    project_id: UUID
    claim_id: UUID
    source_id: UUID
    source_version_id: UUID
    chunk_id: UUID
    created_by: UUID
    stance: EvidenceStance
    note: str | None = None
    created_at: datetime


class AttachEvidenceRequest(BaseModel):
    chunk_id: UUID
    stance: EvidenceStance
    note: str | None = Field(default=None, max_length=8000)


class CitationCandidate(BaseModel):
    id: UUID
    project_id: UUID
    claim_id: UUID
    evidence_id: UUID
    created_by: UUID
    status: CitationStatus
    created_at: datetime
    updated_at: datetime


class UpdateCitationRequest(BaseModel):
    status: Literal[CitationStatus.ACCEPTED, CitationStatus.REJECTED]


class EvidenceAttachment(BaseModel):
    claim: ResearchClaim
    evidence: ClaimEvidence
    citation: CitationCandidate


class ResearchGapItem(BaseModel):
    kind: ResearchGapKind
    entity_id: UUID
    summary: str
    severity: Literal["low", "medium", "high"]


class ResearchGapReport(BaseModel):
    project_id: UUID
    open_questions: int
    unsupported_claims: int
    disputed_claims: int
    pending_citations: int
    items: list[ResearchGapItem]


class ResearchStructureNotFound(KeyError):
    """A project-scoped research entity was not visible to the caller."""


@runtime_checkable
class ResearchStructureRepository(Protocol):
    async def create_research_question(
        self,
        *,
        access_token: str,
        project_id: UUID,
        question: str,
        priority: int,
    ) -> ResearchQuestion: ...

    async def list_research_questions(
        self, *, access_token: str, project_id: UUID
    ) -> list[ResearchQuestion]: ...

    async def get_research_question(
        self, *, access_token: str, project_id: UUID, question_id: UUID
    ) -> ResearchQuestion | None: ...

    async def update_research_question(
        self,
        *,
        access_token: str,
        project_id: UUID,
        question_id: UUID,
        changes: dict[str, Any],
    ) -> ResearchQuestion: ...

    async def create_claim(
        self, *, access_token: str, project_id: UUID, statement: str
    ) -> ResearchClaim: ...

    async def list_claims(
        self, *, access_token: str, project_id: UUID
    ) -> list[ResearchClaim]: ...

    async def get_claim(
        self, *, access_token: str, project_id: UUID, claim_id: UUID
    ) -> ResearchClaim | None: ...

    async def set_claim_status(
        self,
        *,
        access_token: str,
        project_id: UUID,
        claim_id: UUID,
        claim_status: ClaimStatus,
    ) -> ResearchClaim: ...

    async def create_research_note(
        self,
        *,
        access_token: str,
        project_id: UUID,
        request: CreateResearchNoteRequest,
    ) -> ResearchNote: ...

    async def list_research_notes(
        self, *, access_token: str, project_id: UUID
    ) -> list[ResearchNote]: ...

    async def get_research_chunk(
        self, *, access_token: str, project_id: UUID, chunk_id: UUID
    ) -> SourceChunk | None: ...

    async def create_claim_evidence(
        self,
        *,
        access_token: str,
        project_id: UUID,
        claim_id: UUID,
        chunk: SourceChunk,
        stance: EvidenceStance,
        note: str | None,
    ) -> ClaimEvidence: ...

    async def list_claim_evidence(
        self, *, access_token: str, project_id: UUID, claim_id: UUID
    ) -> list[ClaimEvidence]: ...

    async def get_claim_evidence(
        self, *, access_token: str, project_id: UUID, evidence_id: UUID
    ) -> ClaimEvidence | None: ...

    async def create_citation_candidate(
        self,
        *,
        access_token: str,
        evidence: ClaimEvidence,
    ) -> CitationCandidate: ...

    async def list_citation_candidates(
        self, *, access_token: str, project_id: UUID
    ) -> list[CitationCandidate]: ...

    async def get_citation_candidate(
        self, *, access_token: str, project_id: UUID, citation_id: UUID
    ) -> CitationCandidate | None: ...

    async def update_citation_candidate(
        self,
        *,
        access_token: str,
        project_id: UUID,
        citation_id: UUID,
        citation_status: CitationStatus,
    ) -> CitationCandidate: ...

    async def add_learning_signal(
        self,
        *,
        access_token: str,
        project_id: UUID,
        event_type: LearningEvent,
        entity_type: str | None,
        entity_id: UUID | None,
        metadata: dict[str, Any],
    ) -> Any: ...


class SupabaseResearchRepository(SupabaseRepository):
    """Supabase repository extended with structured research state."""

    async def create_research_question(
        self,
        *,
        access_token: str,
        project_id: UUID,
        question: str,
        priority: int,
    ) -> ResearchQuestion:
        rows = await self._request_rows(
            "POST",
            "/research_questions",
            access_token=access_token,
            json={"project_id": str(project_id), "question": question, "priority": priority},
            prefer="return=representation",
        )
        return self._one(rows, ResearchQuestion)

    async def list_research_questions(
        self, *, access_token: str, project_id: UUID
    ) -> list[ResearchQuestion]:
        rows = await self._request_rows(
            "GET",
            "/research_questions",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "order": "priority.desc,created_at.asc",
            },
        )
        return self._many(rows, ResearchQuestion)

    async def get_research_question(
        self, *, access_token: str, project_id: UUID, question_id: UUID
    ) -> ResearchQuestion | None:
        rows = await self._request_rows(
            "GET",
            "/research_questions",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "id": f"eq.{question_id}",
                "limit": "1",
            },
        )
        return None if not rows else self._one(rows, ResearchQuestion)

    async def update_research_question(
        self,
        *,
        access_token: str,
        project_id: UUID,
        question_id: UUID,
        changes: dict[str, Any],
    ) -> ResearchQuestion:
        rows = await self._request_rows(
            "PATCH",
            "/research_questions",
            access_token=access_token,
            params={"project_id": f"eq.{project_id}", "id": f"eq.{question_id}"},
            json=changes,
            prefer="return=representation",
        )
        return self._one(rows, ResearchQuestion)

    async def create_claim(
        self, *, access_token: str, project_id: UUID, statement: str
    ) -> ResearchClaim:
        rows = await self._request_rows(
            "POST",
            "/research_claims",
            access_token=access_token,
            json={"project_id": str(project_id), "statement": statement},
            prefer="return=representation",
        )
        return self._one(rows, ResearchClaim)

    async def list_claims(
        self, *, access_token: str, project_id: UUID
    ) -> list[ResearchClaim]:
        rows = await self._request_rows(
            "GET",
            "/research_claims",
            access_token=access_token,
            params={"select": "*", "project_id": f"eq.{project_id}", "order": "created_at.asc"},
        )
        return self._many(rows, ResearchClaim)

    async def get_claim(
        self, *, access_token: str, project_id: UUID, claim_id: UUID
    ) -> ResearchClaim | None:
        rows = await self._request_rows(
            "GET",
            "/research_claims",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "id": f"eq.{claim_id}",
                "limit": "1",
            },
        )
        return None if not rows else self._one(rows, ResearchClaim)

    async def set_claim_status(
        self,
        *,
        access_token: str,
        project_id: UUID,
        claim_id: UUID,
        claim_status: ClaimStatus,
    ) -> ResearchClaim:
        rows = await self._request_rows(
            "PATCH",
            "/research_claims",
            access_token=access_token,
            params={"project_id": f"eq.{project_id}", "id": f"eq.{claim_id}"},
            json={"status": claim_status.value},
            prefer="return=representation",
        )
        return self._one(rows, ResearchClaim)

    async def create_research_note(
        self,
        *,
        access_token: str,
        project_id: UUID,
        request: CreateResearchNoteRequest,
    ) -> ResearchNote:
        rows = await self._request_rows(
            "POST",
            "/research_notes",
            access_token=access_token,
            json={
                "project_id": str(project_id),
                "question_id": None if request.question_id is None else str(request.question_id),
                "source_chunk_id": (
                    None if request.source_chunk_id is None else str(request.source_chunk_id)
                ),
                "kind": request.kind.value,
                "title": request.title,
                "body": request.body,
            },
            prefer="return=representation",
        )
        return self._one(rows, ResearchNote)

    async def list_research_notes(
        self, *, access_token: str, project_id: UUID
    ) -> list[ResearchNote]:
        rows = await self._request_rows(
            "GET",
            "/research_notes",
            access_token=access_token,
            params={"select": "*", "project_id": f"eq.{project_id}", "order": "created_at.desc"},
        )
        return self._many(rows, ResearchNote)

    async def get_research_chunk(
        self, *, access_token: str, project_id: UUID, chunk_id: UUID
    ) -> SourceChunk | None:
        rows = await self._request_rows(
            "GET",
            "/source_chunks",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "id": f"eq.{chunk_id}",
                "limit": "1",
            },
        )
        return None if not rows else self._one(rows, SourceChunk)

    async def create_claim_evidence(
        self,
        *,
        access_token: str,
        project_id: UUID,
        claim_id: UUID,
        chunk: SourceChunk,
        stance: EvidenceStance,
        note: str | None,
    ) -> ClaimEvidence:
        rows = await self._request_rows(
            "POST",
            "/claim_evidence",
            access_token=access_token,
            json={
                "project_id": str(project_id),
                "claim_id": str(claim_id),
                "source_id": str(chunk.source_id),
                "source_version_id": str(chunk.source_version_id),
                "chunk_id": str(chunk.id),
                "stance": stance.value,
                "note": note,
            },
            prefer="return=representation",
        )
        return self._one(rows, ClaimEvidence)

    async def list_claim_evidence(
        self, *, access_token: str, project_id: UUID, claim_id: UUID
    ) -> list[ClaimEvidence]:
        rows = await self._request_rows(
            "GET",
            "/claim_evidence",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "claim_id": f"eq.{claim_id}",
                "order": "created_at.asc",
            },
        )
        return self._many(rows, ClaimEvidence)

    async def get_claim_evidence(
        self, *, access_token: str, project_id: UUID, evidence_id: UUID
    ) -> ClaimEvidence | None:
        rows = await self._request_rows(
            "GET",
            "/claim_evidence",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "id": f"eq.{evidence_id}",
                "limit": "1",
            },
        )
        return None if not rows else self._one(rows, ClaimEvidence)

    async def create_citation_candidate(
        self,
        *,
        access_token: str,
        evidence: ClaimEvidence,
    ) -> CitationCandidate:
        rows = await self._request_rows(
            "POST",
            "/citation_candidates",
            access_token=access_token,
            json={
                "project_id": str(evidence.project_id),
                "claim_id": str(evidence.claim_id),
                "evidence_id": str(evidence.id),
            },
            prefer="return=representation",
        )
        return self._one(rows, CitationCandidate)

    async def list_citation_candidates(
        self, *, access_token: str, project_id: UUID
    ) -> list[CitationCandidate]:
        rows = await self._request_rows(
            "GET",
            "/citation_candidates",
            access_token=access_token,
            params={"select": "*", "project_id": f"eq.{project_id}", "order": "created_at.asc"},
        )
        return self._many(rows, CitationCandidate)

    async def get_citation_candidate(
        self, *, access_token: str, project_id: UUID, citation_id: UUID
    ) -> CitationCandidate | None:
        rows = await self._request_rows(
            "GET",
            "/citation_candidates",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "id": f"eq.{citation_id}",
                "limit": "1",
            },
        )
        return None if not rows else self._one(rows, CitationCandidate)

    async def update_citation_candidate(
        self,
        *,
        access_token: str,
        project_id: UUID,
        citation_id: UUID,
        citation_status: CitationStatus,
    ) -> CitationCandidate:
        rows = await self._request_rows(
            "PATCH",
            "/citation_candidates",
            access_token=access_token,
            params={"project_id": f"eq.{project_id}", "id": f"eq.{citation_id}"},
            json={"status": citation_status.value},
            prefer="return=representation",
        )
        return self._one(rows, CitationCandidate)


class ResearchStructureService:
    def __init__(
        self,
        *,
        repository: ResearchStructureRepository,
        research: AuthorizedResearchService | None,
    ) -> None:
        self._repository = repository
        self._research = research

    async def update_question(
        self,
        *,
        access_token: str,
        project_id: UUID,
        question_id: UUID,
        request: UpdateResearchQuestionRequest,
    ) -> ResearchQuestion:
        current = await self._repository.get_research_question(
            access_token=access_token, project_id=project_id, question_id=question_id
        )
        if current is None:
            raise ResearchStructureNotFound(str(question_id))
        changes = request.model_dump(exclude_unset=True, mode="json")
        if not changes:
            raise ValueError("At least one question field must be changed")
        next_status = request.status or current.status
        if next_status is ResearchQuestionStatus.RESOLVED:
            resolution = request.resolution if request.resolution is not None else current.resolution
            if not resolution or not resolution.strip():
                raise ValueError("Resolved research questions require a resolution")
        elif request.status is not None and request.resolution is None:
            changes["resolution"] = None
        return await self._repository.update_research_question(
            access_token=access_token,
            project_id=project_id,
            question_id=question_id,
            changes=changes,
        )

    async def create_note(
        self,
        *,
        access_token: str,
        project_id: UUID,
        request: CreateResearchNoteRequest,
    ) -> ResearchNote:
        if request.question_id is not None:
            question = await self._repository.get_research_question(
                access_token=access_token,
                project_id=project_id,
                question_id=request.question_id,
            )
            if question is None:
                raise ResearchStructureNotFound(str(request.question_id))
        if request.source_chunk_id is not None:
            chunk = await self._repository.get_research_chunk(
                access_token=access_token,
                project_id=project_id,
                chunk_id=request.source_chunk_id,
            )
            if chunk is None:
                raise ResearchStructureNotFound(str(request.source_chunk_id))
        return await self._repository.create_research_note(
            access_token=access_token, project_id=project_id, request=request
        )

    async def attach_evidence(
        self,
        *,
        access_token: str,
        project_id: UUID,
        claim_id: UUID,
        request: AttachEvidenceRequest,
    ) -> EvidenceAttachment:
        claim = await self._repository.get_claim(
            access_token=access_token, project_id=project_id, claim_id=claim_id
        )
        if claim is None:
            raise ResearchStructureNotFound(str(claim_id))
        chunk = await self._repository.get_research_chunk(
            access_token=access_token,
            project_id=project_id,
            chunk_id=request.chunk_id,
        )
        if chunk is None:
            raise ResearchStructureNotFound(str(request.chunk_id))
        evidence = await self._repository.create_claim_evidence(
            access_token=access_token,
            project_id=project_id,
            claim_id=claim_id,
            chunk=chunk,
            stance=request.stance,
            note=request.note,
        )
        citation = await self._repository.create_citation_candidate(
            access_token=access_token,
            evidence=evidence,
        )
        claim = await self._reconcile_claim(
            access_token=access_token, project_id=project_id, claim=claim
        )
        return EvidenceAttachment(claim=claim, evidence=evidence, citation=citation)

    async def search_question(
        self,
        *,
        access_token: str,
        project_id: UUID,
        question_id: UUID,
        limit: int,
    ) -> ResearchResponse:
        question = await self._repository.get_research_question(
            access_token=access_token, project_id=project_id, question_id=question_id
        )
        if question is None:
            raise ResearchStructureNotFound(str(question_id))
        return await self._search_and_record(
            access_token=access_token,
            project_id=project_id,
            query=question.question,
            limit=limit,
            entity_type="research_question",
            entity_id=question.id,
        )

    async def search_claim(
        self,
        *,
        access_token: str,
        project_id: UUID,
        claim_id: UUID,
        limit: int,
    ) -> ResearchResponse:
        claim = await self._repository.get_claim(
            access_token=access_token, project_id=project_id, claim_id=claim_id
        )
        if claim is None:
            raise ResearchStructureNotFound(str(claim_id))
        return await self._search_and_record(
            access_token=access_token,
            project_id=project_id,
            query=claim.statement,
            limit=limit,
            entity_type="research_claim",
            entity_id=claim.id,
        )

    async def update_citation(
        self,
        *,
        access_token: str,
        project_id: UUID,
        citation_id: UUID,
        citation_status: CitationStatus,
    ) -> CitationCandidate:
        citation = await self._repository.get_citation_candidate(
            access_token=access_token,
            project_id=project_id,
            citation_id=citation_id,
        )
        if citation is None:
            raise ResearchStructureNotFound(str(citation_id))
        updated = await self._repository.update_citation_candidate(
            access_token=access_token,
            project_id=project_id,
            citation_id=citation_id,
            citation_status=citation_status,
        )
        event = (
            LearningEvent.CITATION_ACCEPTED
            if citation_status is CitationStatus.ACCEPTED
            else LearningEvent.CITATION_REJECTED
        )
        await self._repository.add_learning_signal(
            access_token=access_token,
            project_id=project_id,
            event_type=event,
            entity_type="citation_candidate",
            entity_id=citation_id,
            metadata={"claim_id": str(citation.claim_id), "evidence_id": str(citation.evidence_id)},
        )
        if citation_status is CitationStatus.ACCEPTED:
            evidence = await self._repository.get_claim_evidence(
                access_token=access_token,
                project_id=project_id,
                evidence_id=citation.evidence_id,
            )
            if evidence is not None:
                await self._repository.add_learning_signal(
                    access_token=access_token,
                    project_id=project_id,
                    event_type=LearningEvent.SOURCE_CITED,
                    entity_type="source_chunk",
                    entity_id=evidence.chunk_id,
                    metadata={"claim_id": str(citation.claim_id)},
                )
        return updated

    async def gap_report(
        self, *, access_token: str, project_id: UUID
    ) -> ResearchGapReport:
        questions = await self._repository.list_research_questions(
            access_token=access_token, project_id=project_id
        )
        claims = await self._repository.list_claims(
            access_token=access_token, project_id=project_id
        )
        citations = await self._repository.list_citation_candidates(
            access_token=access_token, project_id=project_id
        )
        items: list[ResearchGapItem] = []
        open_questions = 0
        unsupported_claims = 0
        disputed_claims = 0
        pending_citations = 0
        for question in questions:
            if question.status in {ResearchQuestionStatus.OPEN, ResearchQuestionStatus.INVESTIGATING}:
                open_questions += 1
                severity: Literal["low", "medium", "high"]
                severity = "high" if question.priority >= 4 else "medium" if question.priority >= 2 else "low"
                items.append(
                    ResearchGapItem(
                        kind=ResearchGapKind.OPEN_QUESTION,
                        entity_id=question.id,
                        summary=question.question,
                        severity=severity,
                    )
                )
        for claim in claims:
            if claim.status is ClaimStatus.NEEDS_EVIDENCE:
                unsupported_claims += 1
                items.append(
                    ResearchGapItem(
                        kind=ResearchGapKind.UNSUPPORTED_CLAIM,
                        entity_id=claim.id,
                        summary=claim.statement,
                        severity="high",
                    )
                )
            elif claim.status is ClaimStatus.DISPUTED:
                disputed_claims += 1
                items.append(
                    ResearchGapItem(
                        kind=ResearchGapKind.DISPUTED_CLAIM,
                        entity_id=claim.id,
                        summary=claim.statement,
                        severity="high",
                    )
                )
        for citation in citations:
            if citation.status is CitationStatus.PROPOSED:
                pending_citations += 1
                items.append(
                    ResearchGapItem(
                        kind=ResearchGapKind.PENDING_CITATION,
                        entity_id=citation.id,
                        summary=f"Citation candidate for claim {citation.claim_id}",
                        severity="medium",
                    )
                )
        return ResearchGapReport(
            project_id=project_id,
            open_questions=open_questions,
            unsupported_claims=unsupported_claims,
            disputed_claims=disputed_claims,
            pending_citations=pending_citations,
            items=items,
        )

    async def _reconcile_claim(
        self,
        *,
        access_token: str,
        project_id: UUID,
        claim: ResearchClaim,
    ) -> ResearchClaim:
        evidence = await self._repository.list_claim_evidence(
            access_token=access_token,
            project_id=project_id,
            claim_id=claim.id,
        )
        stances = {item.stance for item in evidence}
        if EvidenceStance.CONTRADICTS in stances:
            next_status = ClaimStatus.DISPUTED
        elif EvidenceStance.SUPPORTS in stances:
            next_status = ClaimStatus.SUPPORTED
        else:
            next_status = ClaimStatus.NEEDS_EVIDENCE
        if next_status is claim.status:
            return claim
        return await self._repository.set_claim_status(
            access_token=access_token,
            project_id=project_id,
            claim_id=claim.id,
            claim_status=next_status,
        )

    async def _search_and_record(
        self,
        *,
        access_token: str,
        project_id: UUID,
        query: str,
        limit: int,
        entity_type: str,
        entity_id: UUID,
    ) -> ResearchResponse:
        if self._research is None:
            raise ResearchError("MindsDB research is disabled")
        response = await self._research.query(
            access_token=access_token,
            project_id=project_id,
            query=query,
            limit=limit,
        )
        await self._repository.add_learning_signal(
            access_token=access_token,
            project_id=project_id,
            event_type=LearningEvent.RESEARCH_RESULT_IMPRESSION,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata={
                "hit_count": len(response.hits),
                "chunk_ids": [str(hit.chunk_id) for hit in response.hits],
            },
        )
        return response


def register_research_structure_routes(
    *,
    app: FastAPI,
    repository: ResearchStructureRepository,
    research: AuthorizedResearchService | None,
    access_token_dependency: Callable[..., str],
) -> None:
    service = ResearchStructureService(repository=repository, research=research)

    @app.get(
        "/api/projects/{project_id}/research/questions",
        response_model=list[ResearchQuestion],
    )
    async def list_research_questions(
        project_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> list[ResearchQuestion]:
        return await repository.list_research_questions(
            access_token=access_token, project_id=project_id
        )

    @app.post(
        "/api/projects/{project_id}/research/questions",
        response_model=ResearchQuestion,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_research_question(
        project_id: UUID,
        request: CreateResearchQuestionRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> ResearchQuestion:
        return await repository.create_research_question(
            access_token=access_token,
            project_id=project_id,
            question=request.question,
            priority=request.priority,
        )

    @app.patch(
        "/api/projects/{project_id}/research/questions/{question_id}",
        response_model=ResearchQuestion,
    )
    async def update_research_question(
        project_id: UUID,
        question_id: UUID,
        request: UpdateResearchQuestionRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> ResearchQuestion:
        try:
            return await service.update_question(
                access_token=access_token,
                project_id=project_id,
                question_id=question_id,
                request=request,
            )
        except ResearchStructureNotFound as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.post(
        "/api/projects/{project_id}/research/questions/{question_id}/search",
        response_model=ResearchResponse,
    )
    async def search_research_question(
        project_id: UUID,
        question_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
        limit: int = 8,
    ) -> ResearchResponse:
        try:
            return await service.search_question(
                access_token=access_token,
                project_id=project_id,
                question_id=question_id,
                limit=limit,
            )
        except ResearchStructureNotFound as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found") from exc

    @app.get(
        "/api/projects/{project_id}/research/claims",
        response_model=list[ResearchClaim],
    )
    async def list_claims(
        project_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> list[ResearchClaim]:
        return await repository.list_claims(access_token=access_token, project_id=project_id)

    @app.post(
        "/api/projects/{project_id}/research/claims",
        response_model=ResearchClaim,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_claim(
        project_id: UUID,
        request: CreateClaimRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> ResearchClaim:
        return await repository.create_claim(
            access_token=access_token, project_id=project_id, statement=request.statement
        )

    @app.post(
        "/api/projects/{project_id}/research/claims/{claim_id}/search",
        response_model=ResearchResponse,
    )
    async def search_claim(
        project_id: UUID,
        claim_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
        limit: int = 8,
    ) -> ResearchResponse:
        try:
            return await service.search_claim(
                access_token=access_token,
                project_id=project_id,
                claim_id=claim_id,
                limit=limit,
            )
        except ResearchStructureNotFound as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found") from exc

    @app.get(
        "/api/projects/{project_id}/research/claims/{claim_id}/evidence",
        response_model=list[ClaimEvidence],
    )
    async def list_claim_evidence(
        project_id: UUID,
        claim_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> list[ClaimEvidence]:
        return await repository.list_claim_evidence(
            access_token=access_token, project_id=project_id, claim_id=claim_id
        )

    @app.post(
        "/api/projects/{project_id}/research/claims/{claim_id}/evidence",
        response_model=EvidenceAttachment,
        status_code=status.HTTP_201_CREATED,
    )
    async def attach_claim_evidence(
        project_id: UUID,
        claim_id: UUID,
        request: AttachEvidenceRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> EvidenceAttachment:
        try:
            return await service.attach_evidence(
                access_token=access_token,
                project_id=project_id,
                claim_id=claim_id,
                request=request,
            )
        except ResearchStructureNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Claim or source chunk not found"
            ) from exc

    @app.get(
        "/api/projects/{project_id}/research/notes",
        response_model=list[ResearchNote],
    )
    async def list_research_notes(
        project_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> list[ResearchNote]:
        return await repository.list_research_notes(
            access_token=access_token, project_id=project_id
        )

    @app.post(
        "/api/projects/{project_id}/research/notes",
        response_model=ResearchNote,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_research_note(
        project_id: UUID,
        request: CreateResearchNoteRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> ResearchNote:
        try:
            return await service.create_note(
                access_token=access_token, project_id=project_id, request=request
            )
        except ResearchStructureNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question or source chunk not found",
            ) from exc

    @app.get(
        "/api/projects/{project_id}/research/citations",
        response_model=list[CitationCandidate],
    )
    async def list_citation_candidates(
        project_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> list[CitationCandidate]:
        return await repository.list_citation_candidates(
            access_token=access_token, project_id=project_id
        )

    @app.patch(
        "/api/projects/{project_id}/research/citations/{citation_id}",
        response_model=CitationCandidate,
    )
    async def update_citation_candidate(
        project_id: UUID,
        citation_id: UUID,
        request: UpdateCitationRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> CitationCandidate:
        try:
            return await service.update_citation(
                access_token=access_token,
                project_id=project_id,
                citation_id=citation_id,
                citation_status=request.status,
            )
        except ResearchStructureNotFound as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Citation not found") from exc

    @app.get(
        "/api/projects/{project_id}/research/gaps",
        response_model=ResearchGapReport,
    )
    async def research_gap_report(
        project_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> ResearchGapReport:
        return await service.gap_report(access_token=access_token, project_id=project_id)
