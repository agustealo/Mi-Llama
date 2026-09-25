from collections.abc import Callable

from fastapi import FastAPI

from mi_llama.providers.base import StructuredModelProvider
from mi_llama.research import AuthorizedResearchService
from mi_llama.writing_intelligence.models import (
    AnalyzeManuscriptRequest,
    CandidateRelation,
    EvidenceAssessment,
    EvidenceCoverageSummary,
    FindingPromotionResult,
    PromoteFindingRequest,
    ReviewWritingFindingRequest,
    WritingAnalysisFinding,
    WritingAnalysisResult,
    WritingAnalysisRun,
    WritingFindingCandidate,
    WritingFindingStatus,
    WritingFindingWithCandidates,
)
from mi_llama.writing_intelligence.repository import WritingIntelligenceRepository
from mi_llama.writing_intelligence.routes import (
    register_writing_intelligence_routes as _register_writing_intelligence_routes,
)
from mi_llama.writing_intelligence.service import (
    WritingIntelligenceError,
    WritingIntelligenceService,
    WritingIntelligenceUnavailableError,
    WritingIntelligenceValidationError,
)
from mi_llama.writing_studio.repository import (
    SupabaseWritingStudioRepository,
    WritingStudioRepository,
)
from mi_llama.writing_studio.routes import register_writing_studio_routes

SupabaseWritingIntelligenceRepository = SupabaseWritingStudioRepository


def register_writing_intelligence_routes(
    *,
    app: FastAPI,
    repository: WritingIntelligenceRepository,
    provider: StructuredModelProvider | None,
    research: AuthorizedResearchService | None,
    access_token_dependency: Callable[..., str],
) -> None:
    _register_writing_intelligence_routes(
        app=app,
        repository=repository,
        provider=provider,
        research=research,
        access_token_dependency=access_token_dependency,
    )
    if provider is not None and isinstance(repository, WritingStudioRepository):
        register_writing_studio_routes(
            app=app,
            repository=repository,
            provider=provider,
            access_token_dependency=access_token_dependency,
        )


__all__ = [
    "AnalyzeManuscriptRequest",
    "CandidateRelation",
    "EvidenceAssessment",
    "EvidenceCoverageSummary",
    "FindingPromotionResult",
    "PromoteFindingRequest",
    "ReviewWritingFindingRequest",
    "SupabaseWritingIntelligenceRepository",
    "WritingAnalysisFinding",
    "WritingAnalysisResult",
    "WritingAnalysisRun",
    "WritingFindingCandidate",
    "WritingFindingStatus",
    "WritingFindingWithCandidates",
    "WritingIntelligenceError",
    "WritingIntelligenceRepository",
    "WritingIntelligenceService",
    "WritingIntelligenceUnavailableError",
    "WritingIntelligenceValidationError",
    "register_writing_intelligence_routes",
]
