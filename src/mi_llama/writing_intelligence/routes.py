from __future__ import annotations

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status

from mi_llama.providers.base import StructuredModelProvider
from mi_llama.providers.errors import ProviderError
from mi_llama.research import AuthorizedResearchService
from mi_llama.writing_intelligence.models import (
    AnalyzeManuscriptRequest,
    EvidenceCoverageSummary,
    FindingPromotionResult,
    PromoteFindingRequest,
    ReviewWritingFindingRequest,
    WritingAnalysisFinding,
    WritingAnalysisResult,
    WritingAnalysisRun,
)
from mi_llama.writing_intelligence.repository import WritingIntelligenceRepository
from mi_llama.writing_intelligence.service import (
    WritingIntelligenceError,
    WritingIntelligenceService,
    WritingIntelligenceUnavailableError,
    WritingIntelligenceValidationError,
)
from mi_llama.writing_structure.models import WritingStructureNotFound


def register_writing_intelligence_routes(
    *,
    app: FastAPI,
    repository: WritingIntelligenceRepository,
    provider: StructuredModelProvider | None,
    research: AuthorizedResearchService | None,
    access_token_dependency: Callable[..., str],
) -> None:
    service = WritingIntelligenceService(
        repository=repository,
        provider=provider,
        research=research,
    )

    @app.post(
        "/api/projects/{project_id}/writing/documents/{document_id}/analysis",
        response_model=WritingAnalysisResult,
        status_code=status.HTTP_201_CREATED,
    )
    async def analyze_manuscript(
        project_id: UUID,
        document_id: UUID,
        request: AnalyzeManuscriptRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> WritingAnalysisResult:
        try:
            return await service.analyze(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                request=request,
            )
        except WritingStructureNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Manuscript document or revision not found",
            ) from exc
        except WritingIntelligenceValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        except WritingIntelligenceUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        except (WritingIntelligenceError, ProviderError) as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc

    @app.get(
        "/api/projects/{project_id}/writing/documents/{document_id}/analysis",
        response_model=list[WritingAnalysisRun],
    )
    async def list_manuscript_analyses(
        project_id: UUID,
        document_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> list[WritingAnalysisRun]:
        return await repository.list_writing_analysis_runs(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )

    @app.get(
        "/api/projects/{project_id}/writing/documents/{document_id}/analysis/{analysis_id}",
        response_model=WritingAnalysisResult,
    )
    async def get_manuscript_analysis(
        project_id: UUID,
        document_id: UUID,
        analysis_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> WritingAnalysisResult:
        try:
            return await service.get_analysis(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                analysis_id=analysis_id,
            )
        except WritingStructureNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Writing analysis not found",
            ) from exc

    @app.patch(
        "/api/projects/{project_id}/writing/documents/{document_id}/findings/{finding_id}",
        response_model=WritingAnalysisFinding,
    )
    async def review_writing_finding(
        project_id: UUID,
        document_id: UUID,
        finding_id: UUID,
        request: ReviewWritingFindingRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> WritingAnalysisFinding:
        try:
            return await service.review_finding(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                finding_id=finding_id,
                status=request.status,
            )
        except WritingStructureNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Writing finding not found",
            ) from exc
        except WritingIntelligenceValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    @app.post(
        "/api/projects/{project_id}/writing/documents/{document_id}/findings/"
        "{finding_id}/research-question",
        response_model=FindingPromotionResult,
        status_code=status.HTTP_201_CREATED,
    )
    async def promote_writing_finding(
        project_id: UUID,
        document_id: UUID,
        finding_id: UUID,
        request: PromoteFindingRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> FindingPromotionResult:
        try:
            return await service.promote_finding_to_question(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                finding_id=finding_id,
                priority=request.priority,
            )
        except WritingStructureNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Writing finding not found",
            ) from exc
        except WritingIntelligenceValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    @app.get(
        "/api/projects/{project_id}/writing/documents/{document_id}/evidence-coverage",
        response_model=EvidenceCoverageSummary,
    )
    async def evidence_coverage(
        project_id: UUID,
        document_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> EvidenceCoverageSummary:
        return await service.evidence_coverage(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
