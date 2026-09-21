from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from mi_llama.domain import LearningEvent, SourceChunk
from mi_llama.repositories import SupabaseRepository
from mi_llama.research_structure.models import (
    CitationCandidate,
    CitationStatus,
    ClaimEvidence,
    CreateResearchNoteRequest,
    EvidenceStance,
    ResearchClaim,
    ResearchNote,
    ResearchQuestion,
)


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
        self,
        *,
        access_token: str,
        project_id: UUID,
    ) -> list[ResearchQuestion]: ...

    async def get_research_question(
        self,
        *,
        access_token: str,
        project_id: UUID,
        question_id: UUID,
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
        self,
        *,
        access_token: str,
        project_id: UUID,
        statement: str,
    ) -> ResearchClaim: ...

    async def list_claims(
        self,
        *,
        access_token: str,
        project_id: UUID,
    ) -> list[ResearchClaim]: ...

    async def get_claim(
        self,
        *,
        access_token: str,
        project_id: UUID,
        claim_id: UUID,
    ) -> ResearchClaim | None: ...

    async def create_research_note(
        self,
        *,
        access_token: str,
        project_id: UUID,
        request: CreateResearchNoteRequest,
    ) -> ResearchNote: ...

    async def list_research_notes(
        self,
        *,
        access_token: str,
        project_id: UUID,
    ) -> list[ResearchNote]: ...

    async def get_research_chunk(
        self,
        *,
        access_token: str,
        project_id: UUID,
        chunk_id: UUID,
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
        self,
        *,
        access_token: str,
        project_id: UUID,
        claim_id: UUID,
    ) -> list[ClaimEvidence]: ...

    async def get_claim_evidence(
        self,
        *,
        access_token: str,
        project_id: UUID,
        evidence_id: UUID,
    ) -> ClaimEvidence | None: ...

    async def get_citation_candidate_by_evidence(
        self,
        *,
        access_token: str,
        project_id: UUID,
        evidence_id: UUID,
    ) -> CitationCandidate | None: ...

    async def list_citation_candidates(
        self,
        *,
        access_token: str,
        project_id: UUID,
    ) -> list[CitationCandidate]: ...

    async def get_citation_candidate(
        self,
        *,
        access_token: str,
        project_id: UUID,
        citation_id: UUID,
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
            json={
                "project_id": str(project_id),
                "question": question,
                "priority": priority,
            },
            prefer="return=representation",
        )
        return self._one(rows, ResearchQuestion)

    async def list_research_questions(
        self,
        *,
        access_token: str,
        project_id: UUID,
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
        self,
        *,
        access_token: str,
        project_id: UUID,
        question_id: UUID,
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
            params={
                "project_id": f"eq.{project_id}",
                "id": f"eq.{question_id}",
            },
            json=changes,
            prefer="return=representation",
        )
        return self._one(rows, ResearchQuestion)

    async def create_claim(
        self,
        *,
        access_token: str,
        project_id: UUID,
        statement: str,
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
        self,
        *,
        access_token: str,
        project_id: UUID,
    ) -> list[ResearchClaim]:
        rows = await self._request_rows(
            "GET",
            "/research_claims",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "order": "created_at.asc",
            },
        )
        return self._many(rows, ResearchClaim)

    async def get_claim(
        self,
        *,
        access_token: str,
        project_id: UUID,
        claim_id: UUID,
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
                "question_id": (
                    None
                    if request.question_id is None
                    else str(request.question_id)
                ),
                "source_chunk_id": (
                    None
                    if request.source_chunk_id is None
                    else str(request.source_chunk_id)
                ),
                "kind": request.kind.value,
                "title": request.title,
                "body": request.body,
            },
            prefer="return=representation",
        )
        return self._one(rows, ResearchNote)

    async def list_research_notes(
        self,
        *,
        access_token: str,
        project_id: UUID,
    ) -> list[ResearchNote]:
        rows = await self._request_rows(
            "GET",
            "/research_notes",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "order": "created_at.desc",
            },
        )
        return self._many(rows, ResearchNote)

    async def get_research_chunk(
        self,
        *,
        access_token: str,
        project_id: UUID,
        chunk_id: UUID,
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
        self,
        *,
        access_token: str,
        project_id: UUID,
        claim_id: UUID,
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
        self,
        *,
        access_token: str,
        project_id: UUID,
        evidence_id: UUID,
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

    async def get_citation_candidate_by_evidence(
        self,
        *,
        access_token: str,
        project_id: UUID,
        evidence_id: UUID,
    ) -> CitationCandidate | None:
        rows = await self._request_rows(
            "GET",
            "/citation_candidates",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "evidence_id": f"eq.{evidence_id}",
                "limit": "1",
            },
        )
        return None if not rows else self._one(rows, CitationCandidate)

    async def list_citation_candidates(
        self,
        *,
        access_token: str,
        project_id: UUID,
    ) -> list[CitationCandidate]:
        rows = await self._request_rows(
            "GET",
            "/citation_candidates",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "order": "created_at.asc",
            },
        )
        return self._many(rows, CitationCandidate)

    async def get_citation_candidate(
        self,
        *,
        access_token: str,
        project_id: UUID,
        citation_id: UUID,
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
            params={
                "project_id": f"eq.{project_id}",
                "id": f"eq.{citation_id}",
            },
            json={"status": citation_status.value},
            prefer="return=representation",
        )
        return self._one(rows, CitationCandidate)
