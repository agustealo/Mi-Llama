from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from mi_llama.domain import ResearchHit, ResearchResponse
from mi_llama.writing_intelligence import (
    AnalyzeManuscriptRequest,
    CandidateRelation,
    EvidenceAssessment,
    WritingAnalysisFinding,
    WritingAnalysisRun,
    WritingFindingCandidate,
    WritingFindingStatus,
    WritingIntelligenceService,
)
from mi_llama.writing_intelligence.models import FindingDraft
from mi_llama.writing_structure import ManuscriptDocument, ManuscriptRevision, ManuscriptStatus

PROJECT_ID = UUID("11111111-1111-1111-1111-111111111111")
USER_ID = UUID("22222222-2222-2222-2222-222222222222")
DOCUMENT_ID = UUID("33333333-3333-3333-3333-333333333333")
REVISION_ID = UUID("44444444-4444-4444-4444-444444444444")
SOURCE_ID = UUID("55555555-5555-5555-5555-555555555555")
SOURCE_VERSION_ID = UUID("66666666-6666-6666-6666-666666666666")
CHUNK_ID = UUID("77777777-7777-7777-7777-777777777777")


def _now() -> datetime:
    return datetime.now(UTC)


class FakeStructuredProvider:
    def __init__(self, *, relation: str = "supports") -> None:
        self.relation = relation
        self.calls = 0

    async def chat_json(
        self,
        *,
        model: str,
        messages: Any,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        del model, messages
        self.calls += 1
        if schema.get("title") == "ClaimSelectionPayload":
            return {
                "claims": [
                    {
                        "sentence_index": 0,
                        "search_query": "Timbuktu learning center",
                        "rationale": "Externally verifiable historical claim",
                    }
                ]
            }
        return {
            "explanation": "The retrieved passage directly addresses the manuscript claim.",
            "candidates": [{"candidate_index": 0, "relation": self.relation}],
        }


class FakeResearch:
    def __init__(self, *, with_hits: bool = True) -> None:
        self.with_hits = with_hits

    async def query(
        self,
        *,
        access_token: str,
        project_id: UUID,
        query: str,
        limit: int,
    ) -> ResearchResponse:
        del access_token, query, limit
        hits = []
        if self.with_hits:
            hits = [
                ResearchHit(
                    source_id=SOURCE_ID,
                    source_version_id=SOURCE_VERSION_ID,
                    chunk_id=CHUNK_ID,
                    source_filename="history.pdf",
                    location="page 17",
                    ordinal=3,
                    content=(
                        "Timbuktu was a major center of Islamic scholarship and manuscript culture."
                    ),
                    relevance=0.93,
                )
            ]
        return ResearchResponse(project_id=project_id, query="query", hits=hits)


class FakeRepository:
    def __init__(self) -> None:
        now = _now()
        self.document = ManuscriptDocument(
            id=DOCUMENT_ID,
            project_id=PROJECT_ID,
            outline_node_id=None,
            created_by=USER_ID,
            title="Chapter",
            status=ManuscriptStatus.DRAFTING,
            current_revision_id=REVISION_ID,
            current_word_count=11,
            created_at=now,
            updated_at=now,
        )
        self.revision = ManuscriptRevision(
            id=REVISION_ID,
            document_id=DOCUMENT_ID,
            project_id=PROJECT_ID,
            revision_number=1,
            created_by=USER_ID,
            content=(
                "Timbuktu was a major center of learning before 1500. "
                "This chapter next discusses trade."
            ),
            word_count=15,
            created_at=now,
        )
        self.run: WritingAnalysisRun | None = None
        self.findings: list[WritingAnalysisFinding] = []
        self.candidates: list[WritingFindingCandidate] = []

    async def get_manuscript_document(
        self, *, access_token: str, project_id: UUID, document_id: UUID
    ) -> ManuscriptDocument | None:
        del access_token
        return self.document if (project_id, document_id) == (PROJECT_ID, DOCUMENT_ID) else None

    async def get_manuscript_revision(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        revision_id: UUID,
    ) -> ManuscriptRevision | None:
        del access_token
        if (project_id, document_id, revision_id) == (PROJECT_ID, DOCUMENT_ID, REVISION_ID):
            return self.revision
        return None

    async def persist_writing_analysis(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        revision_id: UUID,
        model: str,
        character_start: int,
        character_end: int,
        findings: list[FindingDraft],
    ) -> WritingAnalysisRun:
        del access_token
        now = _now()
        self.run = WritingAnalysisRun(
            id=uuid4(),
            project_id=project_id,
            document_id=document_id,
            revision_id=revision_id,
            created_by=USER_ID,
            model=model,
            character_start=character_start,
            character_end=character_end,
            created_at=now,
        )
        self.findings = []
        self.candidates = []
        for draft in findings:
            finding_id = uuid4()
            self.findings.append(
                WritingAnalysisFinding(
                    id=finding_id,
                    analysis_id=self.run.id,
                    project_id=project_id,
                    document_id=document_id,
                    revision_id=revision_id,
                    created_by=USER_ID,
                    character_start=draft.character_start,
                    character_end=draft.character_end,
                    statement=draft.statement,
                    search_query=draft.search_query,
                    assessment=draft.assessment,
                    explanation=draft.explanation,
                    status=WritingFindingStatus.PROPOSED,
                    research_question_id=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            for candidate in draft.candidates:
                self.candidates.append(
                    WritingFindingCandidate(
                        id=uuid4(),
                        analysis_id=self.run.id,
                        finding_id=finding_id,
                        project_id=project_id,
                        chunk_id=candidate.chunk_id,
                        source_id=candidate.source_id,
                        source_version_id=candidate.source_version_id,
                        created_by=USER_ID,
                        rank=candidate.rank,
                        relevance=candidate.relevance,
                        relation=candidate.relation,
                        created_at=now,
                    )
                )
        return self.run

    async def get_writing_analysis_run(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        analysis_id: UUID,
    ) -> WritingAnalysisRun | None:
        del access_token
        if (
            self.run is not None
            and self.run.project_id == project_id
            and self.run.document_id == document_id
            and self.run.id == analysis_id
        ):
            return self.run
        return None

    async def list_writing_analysis_findings(
        self, *, access_token: str, project_id: UUID, analysis_id: UUID
    ) -> list[WritingAnalysisFinding]:
        del access_token
        return [
            finding
            for finding in self.findings
            if finding.project_id == project_id and finding.analysis_id == analysis_id
        ]

    async def list_writing_finding_candidates(
        self, *, access_token: str, project_id: UUID, analysis_id: UUID
    ) -> list[WritingFindingCandidate]:
        del access_token
        return [
            candidate
            for candidate in self.candidates
            if candidate.project_id == project_id and candidate.analysis_id == analysis_id
        ]


@pytest.mark.asyncio
async def test_analysis_derives_supported_only_from_candidate_relations() -> None:
    repository = FakeRepository()
    provider = FakeStructuredProvider(relation="supports")
    service = WritingIntelligenceService(
        repository=repository,  # type: ignore[arg-type]
        provider=provider,
        research=FakeResearch(),  # type: ignore[arg-type]
    )

    result = await service.analyze(
        access_token="jwt",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        request=AnalyzeManuscriptRequest(model="llama3.2:latest"),
    )

    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.finding.assessment is EvidenceAssessment.SUPPORTED
    assert finding.candidates[0].relation is CandidateRelation.SUPPORTS
    assert finding.finding.statement.startswith("Timbuktu")
    assert finding.finding.character_start == 0


@pytest.mark.asyncio
async def test_contradicting_candidate_overrides_support_status() -> None:
    repository = FakeRepository()
    provider = FakeStructuredProvider(relation="contradicts")
    service = WritingIntelligenceService(
        repository=repository,  # type: ignore[arg-type]
        provider=provider,
        research=FakeResearch(),  # type: ignore[arg-type]
    )

    result = await service.analyze(
        access_token="jwt",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        request=AnalyzeManuscriptRequest(model="llama3.2:latest"),
    )

    assert result.findings[0].finding.assessment is EvidenceAssessment.CONTRADICTED
    assert result.findings[0].candidates[0].relation is CandidateRelation.CONTRADICTS


@pytest.mark.asyncio
async def test_no_research_hits_is_insufficient_without_evidence_judgment_call() -> None:
    repository = FakeRepository()
    provider = FakeStructuredProvider()
    service = WritingIntelligenceService(
        repository=repository,  # type: ignore[arg-type]
        provider=provider,
        research=FakeResearch(with_hits=False),  # type: ignore[arg-type]
    )

    result = await service.analyze(
        access_token="jwt",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        request=AnalyzeManuscriptRequest(model="llama3.2:latest"),
    )

    assert result.findings[0].finding.assessment is EvidenceAssessment.INSUFFICIENT
    assert result.findings[0].candidates == []
    assert provider.calls == 1
