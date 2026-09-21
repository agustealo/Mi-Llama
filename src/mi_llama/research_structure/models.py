from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


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
