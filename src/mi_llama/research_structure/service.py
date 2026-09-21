from __future__ import annotations

from typing import Literal
from uuid import UUID

from mi_llama.domain import LearningEvent, ResearchResponse
from mi_llama.repositories import RepositoryProtocolError
from mi_llama.research import AuthorizedResearchService, ResearchError
from mi_llama.research_structure.models import (
    AttachEvidenceRequest,
    CitationCandidate,
    CitationStatus,
    ClaimStatus,
    CreateResearchNoteRequest,
    EvidenceAttachment,
    ResearchGapItem,
    ResearchGapKind,
    ResearchGapReport,
    ResearchNote,
    ResearchQuestion,
    ResearchQuestionStatus,
    ResearchStructureNotFound,
    UpdateResearchQuestionRequest,
)
from mi_llama.research_structure.repository import ResearchStructureRepository


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
            access_token=access_token,
            project_id=project_id,
            question_id=question_id,
        )
        if current is None:
            raise ResearchStructureNotFound(str(question_id))

        changes = request.model_dump(exclude_unset=True, mode="json")
        if not changes:
            raise ValueError("At least one question field must be changed")

        next_status = request.status or current.status
        if next_status is ResearchQuestionStatus.RESOLVED:
            resolution = (
                request.resolution if request.resolution is not None else current.resolution
            )
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
            access_token=access_token,
            project_id=project_id,
            request=request,
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
            access_token=access_token,
            project_id=project_id,
            claim_id=claim_id,
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

        claim = await self._repository.get_claim(
            access_token=access_token,
            project_id=project_id,
            claim_id=claim_id,
        )
        citation = await self._repository.get_citation_candidate_by_evidence(
            access_token=access_token,
            project_id=project_id,
            evidence_id=evidence.id,
        )
        if claim is None or citation is None:
            raise RepositoryProtocolError(
                "Evidence materialization did not produce claim/citation state"
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
            access_token=access_token,
            project_id=project_id,
            question_id=question_id,
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
            access_token=access_token,
            project_id=project_id,
            claim_id=claim_id,
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
            metadata={
                "claim_id": str(citation.claim_id),
                "evidence_id": str(citation.evidence_id),
            },
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
        self,
        *,
        access_token: str,
        project_id: UUID,
    ) -> ResearchGapReport:
        questions = await self._repository.list_research_questions(
            access_token=access_token,
            project_id=project_id,
        )
        claims = await self._repository.list_claims(
            access_token=access_token,
            project_id=project_id,
        )
        citations = await self._repository.list_citation_candidates(
            access_token=access_token,
            project_id=project_id,
        )

        items: list[ResearchGapItem] = []
        open_questions = 0
        unsupported_claims = 0
        disputed_claims = 0
        pending_citations = 0

        for question in questions:
            if question.status not in {
                ResearchQuestionStatus.OPEN,
                ResearchQuestionStatus.INVESTIGATING,
            }:
                continue
            open_questions += 1
            severity: Literal["low", "medium", "high"]
            if question.priority >= 4:
                severity = "high"
            elif question.priority >= 2:
                severity = "medium"
            else:
                severity = "low"
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
            if citation.status is not CitationStatus.PROPOSED:
                continue
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
