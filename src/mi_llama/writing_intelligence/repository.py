from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from mi_llama.repositories import RepositoryProtocolError
from mi_llama.research_structure.models import ResearchQuestion
from mi_llama.writing_intelligence.models import (
    FindingDraft,
    WritingAnalysisFinding,
    WritingAnalysisRun,
    WritingFindingCandidate,
    WritingFindingStatus,
)
from mi_llama.writing_structure.repository import SupabaseWritingRepository, WritingRepository


@runtime_checkable
class WritingIntelligenceRepository(WritingRepository, Protocol):
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
    ) -> WritingAnalysisRun: ...

    async def list_writing_analysis_runs(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
    ) -> list[WritingAnalysisRun]: ...

    async def get_writing_analysis_run(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        analysis_id: UUID,
    ) -> WritingAnalysisRun | None: ...

    async def list_writing_analysis_findings(
        self,
        *,
        access_token: str,
        project_id: UUID,
        analysis_id: UUID,
    ) -> list[WritingAnalysisFinding]: ...

    async def list_writing_finding_candidates(
        self,
        *,
        access_token: str,
        project_id: UUID,
        analysis_id: UUID,
    ) -> list[WritingFindingCandidate]: ...

    async def get_writing_analysis_finding(
        self,
        *,
        access_token: str,
        project_id: UUID,
        finding_id: UUID,
    ) -> WritingAnalysisFinding | None: ...

    async def review_writing_finding(
        self,
        *,
        access_token: str,
        project_id: UUID,
        finding_id: UUID,
        status: WritingFindingStatus,
    ) -> WritingAnalysisFinding: ...

    async def promote_writing_finding_to_question(
        self,
        *,
        access_token: str,
        project_id: UUID,
        finding_id: UUID,
        priority: int,
    ) -> ResearchQuestion: ...


class SupabaseWritingIntelligenceRepository(SupabaseWritingRepository):
    """Canonical Supabase repository extended with manuscript evidence analysis."""

    async def acquire_conversation_reply_lease(
        self,
        *,
        access_token: str,
        conversation_id: UUID,
        ttl_seconds: int,
    ) -> UUID:
        rows = await self._request_rows(
            "POST",
            "/rpc/acquire_conversation_reply_lease",
            access_token=access_token,
            json={
                "p_conversation_id": str(conversation_id),
                "p_ttl_seconds": ttl_seconds,
            },
        )
        if len(rows) != 1 or rows[0].get("lease_token") is None:
            raise RepositoryProtocolError("Conversation lease RPC returned an invalid token")
        try:
            return UUID(str(rows[0]["lease_token"]))
        except ValueError as exc:
            raise RepositoryProtocolError("Conversation lease RPC returned an invalid UUID") from exc

    async def release_conversation_reply_lease(
        self,
        *,
        access_token: str,
        conversation_id: UUID,
        lease_token: UUID,
    ) -> None:
        await self._request_rows(
            "POST",
            "/rpc/release_conversation_reply_lease",
            access_token=access_token,
            json={
                "p_conversation_id": str(conversation_id),
                "p_lease_token": str(lease_token),
            },
        )

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
        rows = await self._request_rows(
            "POST",
            "/rpc/persist_writing_analysis",
            access_token=access_token,
            json={
                "p_project_id": str(project_id),
                "p_document_id": str(document_id),
                "p_revision_id": str(revision_id),
                "p_model": model,
                "p_character_start": character_start,
                "p_character_end": character_end,
                "p_findings": [finding.model_dump(mode="json") for finding in findings],
            },
        )
        return self._one(rows, WritingAnalysisRun)

    async def list_writing_analysis_runs(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
    ) -> list[WritingAnalysisRun]:
        rows = await self._request_rows(
            "GET",
            "/writing_analysis_runs",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "document_id": f"eq.{document_id}",
                "order": "created_at.desc",
            },
        )
        return self._many(rows, WritingAnalysisRun)

    async def get_writing_analysis_run(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        analysis_id: UUID,
    ) -> WritingAnalysisRun | None:
        rows = await self._request_rows(
            "GET",
            "/writing_analysis_runs",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "document_id": f"eq.{document_id}",
                "id": f"eq.{analysis_id}",
                "limit": "1",
            },
        )
        return None if not rows else self._one(rows, WritingAnalysisRun)

    async def list_writing_analysis_findings(
        self,
        *,
        access_token: str,
        project_id: UUID,
        analysis_id: UUID,
    ) -> list[WritingAnalysisFinding]:
        rows = await self._request_rows(
            "GET",
            "/writing_analysis_findings",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "analysis_id": f"eq.{analysis_id}",
                "order": "character_start.asc,created_at.asc",
            },
        )
        return self._many(rows, WritingAnalysisFinding)

    async def list_writing_finding_candidates(
        self,
        *,
        access_token: str,
        project_id: UUID,
        analysis_id: UUID,
    ) -> list[WritingFindingCandidate]:
        rows = await self._request_rows(
            "GET",
            "/writing_finding_candidates",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "analysis_id": f"eq.{analysis_id}",
                "order": "finding_id.asc,rank.asc",
            },
        )
        return self._many(rows, WritingFindingCandidate)

    async def get_writing_analysis_finding(
        self,
        *,
        access_token: str,
        project_id: UUID,
        finding_id: UUID,
    ) -> WritingAnalysisFinding | None:
        rows = await self._request_rows(
            "GET",
            "/writing_analysis_findings",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "id": f"eq.{finding_id}",
                "limit": "1",
            },
        )
        return None if not rows else self._one(rows, WritingAnalysisFinding)

    async def review_writing_finding(
        self,
        *,
        access_token: str,
        project_id: UUID,
        finding_id: UUID,
        status: WritingFindingStatus,
    ) -> WritingAnalysisFinding:
        rows = await self._request_rows(
            "POST",
            "/rpc/review_writing_finding",
            access_token=access_token,
            json={
                "p_project_id": str(project_id),
                "p_finding_id": str(finding_id),
                "p_status": status.value,
            },
        )
        return self._one(rows, WritingAnalysisFinding)

    async def promote_writing_finding_to_question(
        self,
        *,
        access_token: str,
        project_id: UUID,
        finding_id: UUID,
        priority: int,
    ) -> ResearchQuestion:
        rows = await self._request_rows(
            "POST",
            "/rpc/promote_writing_finding_to_question",
            access_token=access_token,
            json={
                "p_project_id": str(project_id),
                "p_finding_id": str(finding_id),
                "p_priority": priority,
            },
        )
        return self._one(rows, ResearchQuestion)
