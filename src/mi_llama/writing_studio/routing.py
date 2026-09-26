from __future__ import annotations

from collections.abc import Callable
from typing import cast

from fastapi import FastAPI

from mi_llama.providers.base import StructuredModelProvider
from mi_llama.writing_studio.proposal_grounding import (
    GroundedProposalRepository,
    register_grounded_proposal_routes,
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
    if isinstance(repository, GroundedProposalRepository):
        register_grounded_proposal_routes(
            app=app,
            repository=cast(GroundedProposalRepository, repository),
            provider=provider,
            access_token_dependency=access_token_dependency,
        )
    register_proposal_iteration_routes(
        app=app,
        repository=repository,
        provider=provider,
        access_token_dependency=access_token_dependency,
    )
