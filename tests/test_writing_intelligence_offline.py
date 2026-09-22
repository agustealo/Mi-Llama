from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from mi_llama.writing_intelligence import (
    AnalyzeManuscriptRequest,
    WritingAnalysisRun,
    WritingIntelligenceService,
    WritingIntelligenceUnavailableError,
)

PROJECT_ID = UUID("11111111-1111-1111-1111-111111111111")
DOCUMENT_ID = UUID("22222222-2222-2222-2222-222222222222")
REVISION_ID = UUID("33333333-3333-3333-3333-333333333333")
ANALYSIS_ID = UUID("44444444-4444-4444-4444-444444444444")
USER_ID = UUID("55555555-5555-5555-5555-555555555555")


class OfflineRepository:
    def __init__(self) -> None:
        self.run = WritingAnalysisRun(
            id=ANALYSIS_ID,
            project_id=PROJECT_ID,
            document_id=DOCUMENT_ID,
            revision_id=REVISION_ID,
            created_by=USER_ID,
            model="llama3.2:latest",
            character_start=0,
            character_end=10,
            created_at=datetime.now(UTC),
        )

    async def get_writing_analysis_run(self, **_: object) -> WritingAnalysisRun:
        return self.run

    async def list_writing_analysis_findings(self, **_: object) -> list[object]:
        return []

    async def list_writing_finding_candidates(self, **_: object) -> list[object]:
        return []


@pytest.mark.asyncio
async def test_stored_analysis_remains_readable_without_intelligence_engines() -> None:
    service = WritingIntelligenceService(
        repository=OfflineRepository(),  # type: ignore[arg-type]
        provider=None,
        research=None,
    )

    result = await service.get_analysis(
        access_token="jwt",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        analysis_id=ANALYSIS_ID,
    )

    assert result.run.id == ANALYSIS_ID
    assert result.findings == []


@pytest.mark.asyncio
async def test_new_analysis_is_unavailable_without_intelligence_engines() -> None:
    service = WritingIntelligenceService(
        repository=OfflineRepository(),  # type: ignore[arg-type]
        provider=None,
        research=None,
    )

    with pytest.raises(WritingIntelligenceUnavailableError):
        await service.analyze(
            access_token="jwt",
            project_id=PROJECT_ID,
            document_id=DOCUMENT_ID,
            request=AnalyzeManuscriptRequest(model="llama3.2:latest"),
        )
