from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from mi_llama.research_structure.models import ResearchQuestion


class EvidenceAssessment(StrEnum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    INSUFFICIENT = "insufficient"


class CandidateRelation(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CONTEXT = "context"
    UNCLEAR = "unclear"


class WritingFindingStatus(StrEnum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"
    RESEARCH_QUESTION_CREATED = "research_question_created"


class WritingAnalysisRun(BaseModel):
    id: UUID
    project_id: UUID
    document_id: UUID
    revision_id: UUID
    created_by: UUID
    model: str
    character_start: int = Field(ge=0)
    character_end: int = Field(ge=1)
    created_at: datetime


class WritingFindingCandidate(BaseModel):
    id: UUID
    analysis_id: UUID
    finding_id: UUID
    project_id: UUID
    chunk_id: UUID
    source_id: UUID
    source_version_id: UUID
    created_by: UUID
    rank: int = Field(ge=0)
    relevance: float = Field(ge=0)
    relation: CandidateRelation
    created_at: datetime


class WritingAnalysisFinding(BaseModel):
    id: UUID
    analysis_id: UUID
    project_id: UUID
    document_id: UUID
    revision_id: UUID
    created_by: UUID
    character_start: int = Field(ge=0)
    character_end: int = Field(ge=1)
    statement: str
    search_query: str
    assessment: EvidenceAssessment
    explanation: str
    status: WritingFindingStatus
    research_question_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class WritingFindingWithCandidates(BaseModel):
    finding: WritingAnalysisFinding
    candidates: list[WritingFindingCandidate]


class WritingAnalysisResult(BaseModel):
    run: WritingAnalysisRun
    findings: list[WritingFindingWithCandidates]


class AnalyzeManuscriptRequest(BaseModel):
    revision_id: UUID | None = None
    model: str = Field(min_length=1, max_length=200)
    character_start: int | None = Field(default=None, ge=0)
    character_end: int | None = Field(default=None, ge=1)
    max_claims: int = Field(default=12, ge=1, le=20)
    research_limit: int = Field(default=5, ge=1, le=10)


class ReviewWritingFindingRequest(BaseModel):
    status: WritingFindingStatus


class PromoteFindingRequest(BaseModel):
    priority: int = Field(default=3, ge=1, le=5)


class FindingPromotionResult(BaseModel):
    finding: WritingAnalysisFinding
    research_question: ResearchQuestion


class EvidenceCoverageSummary(BaseModel):
    project_id: UUID
    document_id: UUID
    analysis_id: UUID | None = None
    analyzed_revision_id: UUID | None = None
    total_findings: int = 0
    supported: int = 0
    contradicted: int = 0
    insufficient: int = 0
    confirmed: int = 0
    dismissed: int = 0
    research_questions_created: int = 0


class CandidateDraft(BaseModel):
    chunk_id: UUID
    source_id: UUID
    source_version_id: UUID
    rank: int = Field(ge=0)
    relevance: float = Field(ge=0)
    relation: CandidateRelation


class FindingDraft(BaseModel):
    character_start: int = Field(ge=0)
    character_end: int = Field(ge=1)
    statement: str = Field(min_length=1, max_length=8000)
    search_query: str = Field(min_length=1, max_length=4000)
    assessment: EvidenceAssessment
    explanation: str = Field(min_length=1, max_length=8000)
    candidates: list[CandidateDraft]


class ClaimSelectionItem(BaseModel):
    sentence_index: int = Field(ge=0)
    search_query: str = Field(min_length=2, max_length=4000)
    rationale: str = Field(min_length=1, max_length=1000)


class ClaimSelectionPayload(BaseModel):
    claims: list[ClaimSelectionItem]


class CandidateJudgment(BaseModel):
    candidate_index: int = Field(ge=0)
    relation: CandidateRelation


class EvidenceJudgmentPayload(BaseModel):
    explanation: str = Field(min_length=1, max_length=8000)
    candidates: list[CandidateJudgment]
