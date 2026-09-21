from __future__ import annotations

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, status

from mi_llama.domain import ResearchResponse
from mi_llama.research import AuthorizedResearchService
from mi_llama.research_structure.models import (
    AttachEvidenceRequest,
    CitationCandidate,
    ClaimEvidence,
    CreateClaimRequest,
    CreateResearchNoteRequest,
    CreateResearchQuestionRequest,
    EvidenceAttachment,
    ResearchClaim,
    ResearchGapReport,
    ResearchNote,
    ResearchQuestion,
    ResearchStructureNotFound,
    UpdateCitationRequest,
    UpdateResearchQuestionRequest,
)
from mi_llama.research_structure.repository import ResearchStructureRepository
from mi_llama.research_structure.service import ResearchStructureService


def register_research_structure_routes(
    *,
    app: FastAPI,
    repository: ResearchStructureRepository,
    research: AuthorizedResearchService | None,
    access_token_dependency: Callable[..., str],
) -> None:
    service = ResearchStructureService(repository=repository, research=research)

    @app.get(
        "/api/projects/{project_id}/research/questions",
        response_model=list[ResearchQuestion],
    )
    async def list_research_questions(
        project_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> list[ResearchQuestion]:
        return await repository.list_research_questions(
            access_token=access_token,
            project_id=project_id,
        )

    @app.post(
        "/api/projects/{project_id}/research/questions",
        response_model=ResearchQuestion,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_research_question(
        project_id: UUID,
        request: CreateResearchQuestionRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> ResearchQuestion:
        return await repository.create_research_question(
            access_token=access_token,
            project_id=project_id,
            question=request.question,
            priority=request.priority,
        )

    @app.patch(
        "/api/projects/{project_id}/research/questions/{question_id}",
        response_model=ResearchQuestion,
    )
    async def update_research_question(
        project_id: UUID,
        question_id: UUID,
        request: UpdateResearchQuestionRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> ResearchQuestion:
        try:
            return await service.update_question(
                access_token=access_token,
                project_id=project_id,
                question_id=question_id,
                request=request,
            )
        except ResearchStructureNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question not found",
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    @app.post(
        "/api/projects/{project_id}/research/questions/{question_id}/search",
        response_model=ResearchResponse,
    )
    async def search_research_question(
        project_id: UUID,
        question_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
        limit: Annotated[int, Query(ge=1, le=25)] = 8,
    ) -> ResearchResponse:
        try:
            return await service.search_question(
                access_token=access_token,
                project_id=project_id,
                question_id=question_id,
                limit=limit,
            )
        except ResearchStructureNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question not found",
            ) from exc

    @app.get(
        "/api/projects/{project_id}/research/claims",
        response_model=list[ResearchClaim],
    )
    async def list_claims(
        project_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> list[ResearchClaim]:
        return await repository.list_claims(
            access_token=access_token,
            project_id=project_id,
        )

    @app.post(
        "/api/projects/{project_id}/research/claims",
        response_model=ResearchClaim,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_claim(
        project_id: UUID,
        request: CreateClaimRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> ResearchClaim:
        return await repository.create_claim(
            access_token=access_token,
            project_id=project_id,
            statement=request.statement,
        )

    @app.post(
        "/api/projects/{project_id}/research/claims/{claim_id}/search",
        response_model=ResearchResponse,
    )
    async def search_claim(
        project_id: UUID,
        claim_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
        limit: Annotated[int, Query(ge=1, le=25)] = 8,
    ) -> ResearchResponse:
        try:
            return await service.search_claim(
                access_token=access_token,
                project_id=project_id,
                claim_id=claim_id,
                limit=limit,
            )
        except ResearchStructureNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Claim not found",
            ) from exc

    @app.get(
        "/api/projects/{project_id}/research/claims/{claim_id}/evidence",
        response_model=list[ClaimEvidence],
    )
    async def list_claim_evidence(
        project_id: UUID,
        claim_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> list[ClaimEvidence]:
        return await repository.list_claim_evidence(
            access_token=access_token,
            project_id=project_id,
            claim_id=claim_id,
        )

    @app.post(
        "/api/projects/{project_id}/research/claims/{claim_id}/evidence",
        response_model=EvidenceAttachment,
        status_code=status.HTTP_201_CREATED,
    )
    async def attach_claim_evidence(
        project_id: UUID,
        claim_id: UUID,
        request: AttachEvidenceRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> EvidenceAttachment:
        try:
            return await service.attach_evidence(
                access_token=access_token,
                project_id=project_id,
                claim_id=claim_id,
                request=request,
            )
        except ResearchStructureNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Claim or source chunk not found",
            ) from exc

    @app.get(
        "/api/projects/{project_id}/research/notes",
        response_model=list[ResearchNote],
    )
    async def list_research_notes(
        project_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> list[ResearchNote]:
        return await repository.list_research_notes(
            access_token=access_token,
            project_id=project_id,
        )

    @app.post(
        "/api/projects/{project_id}/research/notes",
        response_model=ResearchNote,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_research_note(
        project_id: UUID,
        request: CreateResearchNoteRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> ResearchNote:
        try:
            return await service.create_note(
                access_token=access_token,
                project_id=project_id,
                request=request,
            )
        except ResearchStructureNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question or source chunk not found",
            ) from exc

    @app.get(
        "/api/projects/{project_id}/research/citations",
        response_model=list[CitationCandidate],
    )
    async def list_citation_candidates(
        project_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> list[CitationCandidate]:
        return await repository.list_citation_candidates(
            access_token=access_token,
            project_id=project_id,
        )

    @app.patch(
        "/api/projects/{project_id}/research/citations/{citation_id}",
        response_model=CitationCandidate,
    )
    async def update_citation_candidate(
        project_id: UUID,
        citation_id: UUID,
        request: UpdateCitationRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> CitationCandidate:
        try:
            return await service.update_citation(
                access_token=access_token,
                project_id=project_id,
                citation_id=citation_id,
                citation_status=request.status,
            )
        except ResearchStructureNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Citation not found",
            ) from exc

    @app.get(
        "/api/projects/{project_id}/research/gaps",
        response_model=ResearchGapReport,
    )
    async def research_gap_report(
        project_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> ResearchGapReport:
        return await service.gap_report(
            access_token=access_token,
            project_id=project_id,
        )
