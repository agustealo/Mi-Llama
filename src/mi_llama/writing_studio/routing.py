from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI

from mi_llama.citation_authority import (
    CitationAuthorityRepository,
    register_citation_authority_routes,
)
from mi_llama.providers.base import StructuredModelProvider
from mi_llama.structured_citations import (
    StructuredCitationRepository,
    register_structured_citation_routes,
)
from mi_llama.writing_evidence import (
    WritingEvidenceRepository,
    register_writing_evidence_routes,
)
from mi_llama.writing_studio.proposal_iteration import register_proposal_iteration_routes
from mi_llama.writing_studio.repository import WritingStudioRepository
from mi_llama.writing_studio.routes import register_writing_studio_routes as register_core_routes


def register_writing_studio_routes(
    *,
    app: FastAPI,
    repository: WritingStudioRepository,
    provider: StructuredModelProvider,
    access_token_dependency: Callable[..., str],
) -> None:
    register_core_routes(
        app=app,
        repository=repository,
        provider=provider,
        access_token_dependency=access_token_dependency,
    )
    register_proposal_iteration_routes(
        app=app,
        repository=repository,
        provider=provider,
        access_token_dependency=access_token_dependency,
    )

    if isinstance(repository, WritingEvidenceRepository):
        register_writing_evidence_routes(
            app=app,
            repository=repository,
            access_token_dependency=access_token_dependency,
        )
    if isinstance(repository, CitationAuthorityRepository):
        register_citation_authority_routes(
            app=app,
            repository=repository,
            access_token_dependency=access_token_dependency,
        )
    if isinstance(repository, StructuredCitationRepository):
        register_structured_citation_routes(
            app=app,
            repository=repository,
            access_token_dependency=access_token_dependency,
        )
