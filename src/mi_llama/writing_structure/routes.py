from __future__ import annotations

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status

from mi_llama.writing_structure.models import (
    CreateManuscriptDocumentRequest,
    CreateManuscriptRevisionRequest,
    CreateOutlineNodeRequest,
    CreateWritingResearchLinkRequest,
    ManuscriptDocument,
    ManuscriptRevision,
    ManuscriptRevisionResult,
    OutlineNode,
    UpdateManuscriptDocumentRequest,
    UpdateOutlineNodeRequest,
    WritingResearchLink,
    WritingStructureNotFound,
    WritingValidationError,
    WritingWorkspaceSummary,
)
from mi_llama.writing_structure.repository import WritingRepository
from mi_llama.writing_structure.service import WritingStructureService


def register_writing_structure_routes(
    *,
    app: FastAPI,
    repository: WritingRepository,
    access_token_dependency: Callable[..., str],
) -> None:
    service = WritingStructureService(repository=repository)

    @app.get(
        "/api/projects/{project_id}/writing/outline",
        response_model=list[OutlineNode],
    )
    async def list_outline_nodes(
        project_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> list[OutlineNode]:
        return await repository.list_outline_nodes(
            access_token=access_token,
            project_id=project_id,
        )

    @app.post(
        "/api/projects/{project_id}/writing/outline",
        response_model=OutlineNode,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_outline_node(
        project_id: UUID,
        request: CreateOutlineNodeRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> OutlineNode:
        try:
            return await service.create_outline_node(
                access_token=access_token,
                project_id=project_id,
                request=request,
            )
        except WritingStructureNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent outline node not found",
            ) from exc

    @app.patch(
        "/api/projects/{project_id}/writing/outline/{node_id}",
        response_model=OutlineNode,
    )
    async def update_outline_node(
        project_id: UUID,
        node_id: UUID,
        request: UpdateOutlineNodeRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> OutlineNode:
        try:
            return await service.update_outline_node(
                access_token=access_token,
                project_id=project_id,
                node_id=node_id,
                request=request,
            )
        except WritingStructureNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Outline node not found",
            ) from exc
        except WritingValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    @app.get(
        "/api/projects/{project_id}/writing/documents",
        response_model=list[ManuscriptDocument],
    )
    async def list_manuscript_documents(
        project_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> list[ManuscriptDocument]:
        return await repository.list_manuscript_documents(
            access_token=access_token,
            project_id=project_id,
        )

    @app.post(
        "/api/projects/{project_id}/writing/documents",
        response_model=ManuscriptDocument,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_manuscript_document(
        project_id: UUID,
        request: CreateManuscriptDocumentRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> ManuscriptDocument:
        try:
            return await service.create_document(
                access_token=access_token,
                project_id=project_id,
                request=request,
            )
        except WritingStructureNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Outline node not found",
            ) from exc

    @app.get(
        "/api/projects/{project_id}/writing/documents/{document_id}",
        response_model=ManuscriptDocument,
    )
    async def get_manuscript_document(
        project_id: UUID,
        document_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> ManuscriptDocument:
        document = await repository.get_manuscript_document(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Manuscript document not found",
            )
        return document

    @app.patch(
        "/api/projects/{project_id}/writing/documents/{document_id}",
        response_model=ManuscriptDocument,
    )
    async def update_manuscript_document(
        project_id: UUID,
        document_id: UUID,
        request: UpdateManuscriptDocumentRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> ManuscriptDocument:
        try:
            return await service.update_document(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                request=request,
            )
        except WritingStructureNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Manuscript document or outline node not found",
            ) from exc
        except WritingValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    @app.get(
        "/api/projects/{project_id}/writing/documents/{document_id}/revisions",
        response_model=list[ManuscriptRevision],
    )
    async def list_manuscript_revisions(
        project_id: UUID,
        document_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> list[ManuscriptRevision]:
        return await repository.list_manuscript_revisions(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )

    @app.post(
        "/api/projects/{project_id}/writing/documents/{document_id}/revisions",
        response_model=ManuscriptRevisionResult,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_manuscript_revision(
        project_id: UUID,
        document_id: UUID,
        request: CreateManuscriptRevisionRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> ManuscriptRevisionResult:
        try:
            return await service.create_revision(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                request=request,
            )
        except WritingStructureNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Manuscript document not found",
            ) from exc

    @app.get(
        "/api/projects/{project_id}/writing/documents/{document_id}/research-links",
        response_model=list[WritingResearchLink],
    )
    async def list_writing_research_links(
        project_id: UUID,
        document_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> list[WritingResearchLink]:
        return await repository.list_writing_research_links(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )

    @app.post(
        "/api/projects/{project_id}/writing/documents/{document_id}/research-links",
        response_model=WritingResearchLink,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_writing_research_link(
        project_id: UUID,
        document_id: UUID,
        request: CreateWritingResearchLinkRequest,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> WritingResearchLink:
        try:
            return await service.create_research_link(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                request=request,
            )
        except WritingStructureNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Writing or revision entity not found",
            ) from exc
        except WritingValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    @app.get(
        "/api/projects/{project_id}/writing/summary",
        response_model=WritingWorkspaceSummary,
    )
    async def writing_workspace_summary(
        project_id: UUID,
        access_token: Annotated[str, Depends(access_token_dependency)],
    ) -> WritingWorkspaceSummary:
        return await service.workspace_summary(
            access_token=access_token,
            project_id=project_id,
        )
