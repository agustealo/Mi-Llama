from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from mi_llama.writing_structure.models import (
    CreateManuscriptDocumentRequest,
    CreateManuscriptRevisionRequest,
    CreateOutlineNodeRequest,
    CreateWritingResearchLinkRequest,
    ManuscriptDocument,
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


@runtime_checkable
class AtomicRevisionRepository(Protocol):
    async def create_manuscript_revision_result(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        content: str,
    ) -> ManuscriptRevisionResult: ...


class WritingStructureService:
    def __init__(self, *, repository: WritingRepository) -> None:
        self._repository = repository

    async def create_outline_node(
        self,
        *,
        access_token: str,
        project_id: UUID,
        request: CreateOutlineNodeRequest,
    ) -> OutlineNode:
        if request.parent_id is not None:
            parent = await self._repository.get_outline_node(
                access_token=access_token,
                project_id=project_id,
                node_id=request.parent_id,
            )
            if parent is None:
                raise WritingStructureNotFound(str(request.parent_id))
        return await self._repository.create_outline_node(
            access_token=access_token,
            project_id=project_id,
            parent_id=request.parent_id,
            kind=request.kind,
            title=request.title,
            summary=request.summary,
            position=request.position,
        )

    async def update_outline_node(
        self,
        *,
        access_token: str,
        project_id: UUID,
        node_id: UUID,
        request: UpdateOutlineNodeRequest,
    ) -> OutlineNode:
        current = await self._repository.get_outline_node(
            access_token=access_token,
            project_id=project_id,
            node_id=node_id,
        )
        if current is None:
            raise WritingStructureNotFound(str(node_id))

        changes = request.model_dump(exclude_unset=True, mode="json")
        if not changes:
            raise WritingValidationError("At least one outline field must be changed")

        if "parent_id" in changes:
            parent_id = request.parent_id
            if parent_id == node_id:
                raise WritingValidationError("An outline node cannot be its own parent")
            if parent_id is not None:
                parent = await self._repository.get_outline_node(
                    access_token=access_token,
                    project_id=project_id,
                    node_id=parent_id,
                )
                if parent is None:
                    raise WritingStructureNotFound(str(parent_id))

        return await self._repository.update_outline_node(
            access_token=access_token,
            project_id=project_id,
            node_id=node_id,
            changes=changes,
        )

    async def create_document(
        self,
        *,
        access_token: str,
        project_id: UUID,
        request: CreateManuscriptDocumentRequest,
    ) -> ManuscriptDocument:
        if request.outline_node_id is not None:
            node = await self._repository.get_outline_node(
                access_token=access_token,
                project_id=project_id,
                node_id=request.outline_node_id,
            )
            if node is None:
                raise WritingStructureNotFound(str(request.outline_node_id))
        return await self._repository.create_manuscript_document(
            access_token=access_token,
            project_id=project_id,
            outline_node_id=request.outline_node_id,
            title=request.title,
        )

    async def update_document(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        request: UpdateManuscriptDocumentRequest,
    ) -> ManuscriptDocument:
        current = await self._repository.get_manuscript_document(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        if current is None:
            raise WritingStructureNotFound(str(document_id))

        changes = request.model_dump(exclude_unset=True, mode="json")
        if not changes:
            raise WritingValidationError("At least one manuscript field must be changed")

        if "outline_node_id" in changes and request.outline_node_id is not None:
            node = await self._repository.get_outline_node(
                access_token=access_token,
                project_id=project_id,
                node_id=request.outline_node_id,
            )
            if node is None:
                raise WritingStructureNotFound(str(request.outline_node_id))

        return await self._repository.update_manuscript_document(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            changes=changes,
        )

    async def create_revision(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        request: CreateManuscriptRevisionRequest,
    ) -> ManuscriptRevisionResult:
        document = await self._repository.get_manuscript_document(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        if document is None:
            raise WritingStructureNotFound(str(document_id))

        if isinstance(self._repository, AtomicRevisionRepository):
            return await self._repository.create_manuscript_revision_result(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                content=request.content,
            )

        revision = await self._repository.create_manuscript_revision(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            content=request.content,
        )
        updated_document = await self._repository.get_manuscript_document(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        if updated_document is None:
            raise WritingStructureNotFound(str(document_id))
        return ManuscriptRevisionResult(
            document=updated_document,
            revision=revision,
        )

    async def create_research_link(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        request: CreateWritingResearchLinkRequest,
    ) -> WritingResearchLink:
        document = await self._repository.get_manuscript_document(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
        )
        if document is None:
            raise WritingStructureNotFound(str(document_id))

        if request.outline_node_id is not None:
            node = await self._repository.get_outline_node(
                access_token=access_token,
                project_id=project_id,
                node_id=request.outline_node_id,
            )
            if node is None:
                raise WritingStructureNotFound(str(request.outline_node_id))

        has_start = request.character_start is not None
        has_end = request.character_end is not None
        if has_start != has_end:
            raise WritingValidationError(
                "Passage links require both character_start and character_end"
            )
        if request.revision_id is None and (has_start or has_end):
            raise WritingValidationError("Passage anchors require a manuscript revision")
        if has_start and has_end:
            assert request.character_start is not None
            assert request.character_end is not None
            if request.character_end <= request.character_start:
                raise WritingValidationError("character_end must be greater than character_start")

        if request.revision_id is not None:
            revision = await self._repository.get_manuscript_revision(
                access_token=access_token,
                project_id=project_id,
                document_id=document_id,
                revision_id=request.revision_id,
            )
            if revision is None:
                raise WritingStructureNotFound(str(request.revision_id))
            if request.character_end is not None and request.character_end > len(revision.content):
                raise WritingValidationError("Passage anchor exceeds revision content")

        return await self._repository.create_writing_research_link(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            outline_node_id=request.outline_node_id,
            revision_id=request.revision_id,
            kind=request.kind,
            entity_id=request.entity_id,
            character_start=request.character_start,
            character_end=request.character_end,
        )

    async def workspace_summary(
        self,
        *,
        access_token: str,
        project_id: UUID,
    ) -> WritingWorkspaceSummary:
        outline = await self._repository.list_outline_nodes(
            access_token=access_token,
            project_id=project_id,
        )
        documents = await self._repository.list_manuscript_documents(
            access_token=access_token,
            project_id=project_id,
        )
        links = await self._repository.list_writing_research_links(
            access_token=access_token,
            project_id=project_id,
        )
        return WritingWorkspaceSummary(
            project_id=project_id,
            outline_nodes=len(outline),
            manuscript_documents=len(documents),
            current_word_count=sum(document.current_word_count for document in documents),
            research_links=len(links),
        )
