from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from mi_llama.domain import LearningEvent, ResearchHit, ResearchResponse, SourceChunk
from mi_llama.research_structure import (
    AttachEvidenceRequest,
    CitationCandidate,
    CitationStatus,
    ClaimEvidence,
    ClaimStatus,
    CreateResearchNoteRequest,
    EvidenceStance,
    ResearchClaim,
    ResearchGapKind,
    ResearchNote,
    ResearchQuestion,
    ResearchQuestionStatus,
    ResearchStructureService,
    UpdateResearchQuestionRequest,
)

PROJECT_ID = UUID("11111111-1111-1111-1111-111111111111")
USER_ID = UUID("22222222-2222-2222-2222-222222222222")
QUESTION_ID = UUID("33333333-3333-3333-3333-333333333333")
CLAIM_ID = UUID("44444444-4444-4444-4444-444444444444")
SOURCE_ID = UUID("55555555-5555-5555-5555-555555555555")
VERSION_ID = UUID("66666666-6666-6666-6666-666666666666")
CHUNK_ID = UUID("77777777-7777-7777-7777-777777777777")


def _now() -> datetime:
    return datetime.now(UTC)


class FakeResearch:
    async def query(
        self,
        *,
        access_token: str,
        project_id: UUID,
        query: str,
        limit: int,
    ) -> ResearchResponse:
        assert access_token == "jwt"
        assert project_id == PROJECT_ID
        assert limit == 5
        return ResearchResponse(
            project_id=project_id,
            query=query,
            hits=[
                ResearchHit(
                    source_id=SOURCE_ID,
                    source_version_id=VERSION_ID,
                    chunk_id=CHUNK_ID,
                    source_filename="book.pdf",
                    location="page 4",
                    ordinal=0,
                    content="Relevant evidence.",
                    relevance=0.91,
                )
            ],
        )


class FakeStructureRepository:
    def __init__(self) -> None:
        self.question = ResearchQuestion(
            id=QUESTION_ID,
            project_id=PROJECT_ID,
            created_by=USER_ID,
            question="What evidence supports the trade-network thesis?",
            status=ResearchQuestionStatus.OPEN,
            priority=5,
            resolution=None,
            created_at=_now(),
            updated_at=_now(),
        )
        self.claim = ResearchClaim(
            id=CLAIM_ID,
            project_id=PROJECT_ID,
            created_by=USER_ID,
            statement="The trade network connected several regions.",
            status=ClaimStatus.NEEDS_EVIDENCE,
            created_at=_now(),
            updated_at=_now(),
        )
        self.chunk = SourceChunk(
            id=CHUNK_ID,
            source_version_id=VERSION_ID,
            source_id=SOURCE_ID,
            project_id=PROJECT_ID,
            ordinal=0,
            location="page 4",
            content="Relevant evidence.",
            character_start=0,
            character_end=18,
            created_at=_now(),
        )
        self.evidence: list[ClaimEvidence] = []
        self.citations: list[CitationCandidate] = []
        self.signals: list[tuple[LearningEvent, str | None, UUID | None, dict[str, Any]]] = []

    async def get_research_question(
        self, *, access_token: str, project_id: UUID, question_id: UUID
    ) -> ResearchQuestion | None:
        del access_token
        if project_id == PROJECT_ID and question_id == QUESTION_ID:
            return self.question
        return None

    async def update_research_question(
        self,
        *,
        access_token: str,
        project_id: UUID,
        question_id: UUID,
        changes: dict[str, Any],
    ) -> ResearchQuestion:
        del access_token, project_id, question_id
        self.question = self.question.model_copy(update=changes | {"updated_at": _now()})
        return self.question

    async def get_claim(
        self, *, access_token: str, project_id: UUID, claim_id: UUID
    ) -> ResearchClaim | None:
        del access_token
        if project_id == PROJECT_ID and claim_id == CLAIM_ID:
            return self.claim
        return None

    async def get_research_chunk(
        self, *, access_token: str, project_id: UUID, chunk_id: UUID
    ) -> SourceChunk | None:
        del access_token
        if project_id == PROJECT_ID and chunk_id == CHUNK_ID:
            return self.chunk
        return None

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
        del access_token
        item = ClaimEvidence(
            id=uuid4(),
            project_id=project_id,
            claim_id=claim_id,
            source_id=chunk.source_id,
            source_version_id=chunk.source_version_id,
            chunk_id=chunk.id,
            created_by=USER_ID,
            stance=stance,
            note=note,
            created_at=_now(),
        )
        self.evidence.append(item)
        return item

    async def create_citation_candidate(
        self, *, access_token: str, evidence: ClaimEvidence
    ) -> CitationCandidate:
        del access_token
        item = CitationCandidate(
            id=uuid4(),
            project_id=evidence.project_id,
            claim_id=evidence.claim_id,
            evidence_id=evidence.id,
            created_by=USER_ID,
            status=CitationStatus.PROPOSED,
            created_at=_now(),
            updated_at=_now(),
        )
        self.citations.append(item)
        return item

    async def list_claim_evidence(
        self, *, access_token: str, project_id: UUID, claim_id: UUID
    ) -> list[ClaimEvidence]:
        del access_token, project_id
        return [item for item in self.evidence if item.claim_id == claim_id]

    async def set_claim_status(
        self,
        *,
        access_token: str,
        project_id: UUID,
        claim_id: UUID,
        claim_status: ClaimStatus,
    ) -> ResearchClaim:
        del access_token, project_id, claim_id
        self.claim = self.claim.model_copy(update={"status": claim_status, "updated_at": _now()})
        return self.claim

    async def list_research_questions(
        self, *, access_token: str, project_id: UUID
    ) -> list[ResearchQuestion]:
        del access_token, project_id
        return [self.question]

    async def list_claims(
        self, *, access_token: str, project_id: UUID
    ) -> list[ResearchClaim]:
        del access_token, project_id
        disputed = self.claim.model_copy(
            update={"id": uuid4(), "statement": "A disputed claim.", "status": ClaimStatus.DISPUTED}
        )
        return [self.claim, disputed]

    async def list_citation_candidates(
        self, *, access_token: str, project_id: UUID
    ) -> list[CitationCandidate]:
        del access_token, project_id
        return self.citations

    async def add_learning_signal(
        self,
        *,
        access_token: str,
        project_id: UUID,
        event_type: LearningEvent,
        entity_type: str | None,
        entity_id: UUID | None,
        metadata: dict[str, Any],
    ) -> object:
        del access_token, project_id
        self.signals.append((event_type, entity_type, entity_id, metadata))
        return object()

    async def create_research_note(
        self,
        *,
        access_token: str,
        project_id: UUID,
        request: CreateResearchNoteRequest,
    ) -> ResearchNote:
        del access_token
        return ResearchNote(
            id=uuid4(),
            project_id=project_id,
            created_by=USER_ID,
            question_id=request.question_id,
            source_chunk_id=request.source_chunk_id,
            kind=request.kind,
            title=request.title,
            body=request.body,
            created_at=_now(),
            updated_at=_now(),
        )


@pytest.mark.asyncio
async def test_attached_supporting_evidence_updates_claim_and_proposes_citation() -> None:
    repository = FakeStructureRepository()
    service = ResearchStructureService(repository=repository, research=None)  # type: ignore[arg-type]

    result = await service.attach_evidence(
        access_token="jwt",
        project_id=PROJECT_ID,
        claim_id=CLAIM_ID,
        request=AttachEvidenceRequest(chunk_id=CHUNK_ID, stance=EvidenceStance.SUPPORTS),
    )

    assert result.claim.status is ClaimStatus.SUPPORTED
    assert result.evidence.chunk_id == CHUNK_ID
    assert result.citation.status is CitationStatus.PROPOSED


@pytest.mark.asyncio
async def test_resolved_question_requires_resolution_text() -> None:
    repository = FakeStructureRepository()
    service = ResearchStructureService(repository=repository, research=None)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="require a resolution"):
        await service.update_question(
            access_token="jwt",
            project_id=PROJECT_ID,
            question_id=QUESTION_ID,
            request=UpdateResearchQuestionRequest(status=ResearchQuestionStatus.RESOLVED),
        )


@pytest.mark.asyncio
async def test_search_records_project_learning_signal_without_auto_attaching_evidence() -> None:
    repository = FakeStructureRepository()
    service = ResearchStructureService(
        repository=repository,  # type: ignore[arg-type]
        research=FakeResearch(),  # type: ignore[arg-type]
    )

    response = await service.search_question(
        access_token="jwt",
        project_id=PROJECT_ID,
        question_id=QUESTION_ID,
        limit=5,
    )

    assert response.hits[0].chunk_id == CHUNK_ID
    assert repository.evidence == []
    assert repository.signals[0][0] is LearningEvent.RESEARCH_RESULT_IMPRESSION
    assert repository.signals[0][1] == "research_question"


@pytest.mark.asyncio
async def test_gap_report_surfaces_open_questions_claims_and_pending_citations() -> None:
    repository = FakeStructureRepository()
    repository.citations.append(
        CitationCandidate(
            id=uuid4(),
            project_id=PROJECT_ID,
            claim_id=CLAIM_ID,
            evidence_id=uuid4(),
            created_by=USER_ID,
            status=CitationStatus.PROPOSED,
            created_at=_now(),
            updated_at=_now(),
        )
    )
    service = ResearchStructureService(repository=repository, research=None)  # type: ignore[arg-type]

    report = await service.gap_report(access_token="jwt", project_id=PROJECT_ID)

    kinds = {item.kind for item in report.items}
    assert report.open_questions == 1
    assert report.unsupported_claims == 1
    assert report.disputed_claims == 1
    assert report.pending_citations == 1
    assert ResearchGapKind.OPEN_QUESTION in kinds
    assert ResearchGapKind.UNSUPPORTED_CLAIM in kinds
    assert ResearchGapKind.DISPUTED_CLAIM in kinds
    assert ResearchGapKind.PENDING_CITATION in kinds
