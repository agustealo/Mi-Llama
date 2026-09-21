from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from mi_llama.writing_structure import (
    CreateManuscriptRevisionRequest,
    CreateWritingResearchLinkRequest,
    ManuscriptDocument,
    ManuscriptRevision,
    ManuscriptStatus,
    OutlineNode,
    OutlineNodeKind,
    OutlineNodeStatus,
    UpdateOutlineNodeRequest,
    WritingResearchLink,
    WritingResearchLinkKind,
    WritingStructureService,
    WritingValidationError,
)

PROJECT_ID = UUID("11111111-1111-1111-1111-111111111111")
USER_ID = UUID("22222222-2222-2222-2222-222222222222")
NODE_ID = UUID("33333333-3333-3333-3333-333333333333")
DOCUMENT_ID = UUID("44444444-4444-4444-4444-444444444444")
REVISION_ID = UUID("55555555-5555-5555-5555-555555555555")
ENTITY_ID = UUID("66666666-6666-6666-6666-666666666666")


def _now() -> datetime:
    return datetime.now(UTC)


class FakeWritingRepository:
    def __init__(self) -> None:
        now = _now()
        self.node = OutlineNode(
            id=NODE_ID,
            project_id=PROJECT_ID,
            parent_id=None,
            created_by=USER_ID,
            kind=OutlineNodeKind.CHAPTER,
            title="Chapter One",
            summary=None,
            status=OutlineNodeStatus.PLANNED,
            position=0,
            created_at=now,
            updated_at=now,
        )
        self.document = ManuscriptDocument(
            id=DOCUMENT_ID,
            project_id=PROJECT_ID,
            outline_node_id=NODE_ID,
            created_by=USER_ID,
            title="Chapter One",
            status=ManuscriptStatus.DRAFTING,
            current_revision_id=None,
            current_word_count=0,
            created_at=now,
            updated_at=now,
        )
        self.revisions: list[ManuscriptRevision] = []
        self.links: list[WritingResearchLink] = []

    async def get_outline_node(
        self, *, access_token: str, project_id: UUID, node_id: UUID
    ) -> OutlineNode | None:
        del access_token
        if project_id == PROJECT_ID and node_id == NODE_ID:
            return self.node
        return None

    async def update_outline_node(
        self,
        *,
        access_token: str,
        project_id: UUID,
        node_id: UUID,
        changes: dict[str, Any],
    ) -> OutlineNode:
        del access_token, project_id, node_id
        self.node = self.node.model_copy(update=changes | {"updated_at": _now()})
        return self.node

    async def get_manuscript_document(
        self, *, access_token: str, project_id: UUID, document_id: UUID
    ) -> ManuscriptDocument | None:
        del access_token
        if project_id == PROJECT_ID and document_id == DOCUMENT_ID:
            return self.document
        return None

    async def create_manuscript_revision(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        content: str,
    ) -> ManuscriptRevision:
        del access_token
        revision = ManuscriptRevision(
            id=REVISION_ID if not self.revisions else uuid4(),
            document_id=document_id,
            project_id=project_id,
            revision_number=len(self.revisions) + 1,
            created_by=USER_ID,
            content=content,
            word_count=len(content.split()),
            created_at=_now(),
        )
        self.revisions.append(revision)
        self.document = self.document.model_copy(
            update={
                "current_revision_id": revision.id,
                "current_word_count": revision.word_count,
                "updated_at": _now(),
            }
        )
        return revision

    async def get_manuscript_revision(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        revision_id: UUID,
    ) -> ManuscriptRevision | None:
        del access_token
        return next(
            (
                revision
                for revision in self.revisions
                if revision.project_id == project_id
                and revision.document_id == document_id
                and revision.id == revision_id
            ),
            None,
        )

    async def create_writing_research_link(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        outline_node_id: UUID | None,
        revision_id: UUID | None,
        kind: WritingResearchLinkKind,
        entity_id: UUID,
        character_start: int | None,
        character_end: int | None,
    ) -> WritingResearchLink:
        del access_token
        link = WritingResearchLink(
            id=uuid4(),
            project_id=project_id,
            document_id=document_id,
            outline_node_id=outline_node_id,
            revision_id=revision_id,
            created_by=USER_ID,
            kind=kind,
            entity_id=entity_id,
            character_start=character_start,
            character_end=character_end,
            created_at=_now(),
        )
        self.links.append(link)
        return link

    async def list_outline_nodes(self, *, access_token: str, project_id: UUID) -> list[OutlineNode]:
        del access_token, project_id
        return [self.node]

    async def list_manuscript_documents(
        self, *, access_token: str, project_id: UUID
    ) -> list[ManuscriptDocument]:
        del access_token, project_id
        return [self.document]

    async def list_writing_research_links(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID | None = None,
    ) -> list[WritingResearchLink]:
        del access_token
        return [
            link
            for link in self.links
            if link.project_id == project_id
            and (document_id is None or link.document_id == document_id)
        ]


@pytest.mark.asyncio
async def test_revision_write_returns_authoritative_document_word_count() -> None:
    repository = FakeWritingRepository()
    service = WritingStructureService(repository=repository)  # type: ignore[arg-type]

    result = await service.create_revision(
        access_token="jwt",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        request=CreateManuscriptRevisionRequest(content="One two three four."),
    )

    assert result.revision.revision_number == 1
    assert result.revision.word_count == 4
    assert result.document.current_revision_id == result.revision.id
    assert result.document.current_word_count == 4


@pytest.mark.asyncio
async def test_passage_link_is_anchored_to_immutable_revision() -> None:
    repository = FakeWritingRepository()
    service = WritingStructureService(repository=repository)  # type: ignore[arg-type]
    revision_result = await service.create_revision(
        access_token="jwt",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        request=CreateManuscriptRevisionRequest(content="Evidence belongs in this paragraph."),
    )

    link = await service.create_research_link(
        access_token="jwt",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        request=CreateWritingResearchLinkRequest(
            outline_node_id=NODE_ID,
            revision_id=revision_result.revision.id,
            kind=WritingResearchLinkKind.EVIDENCE,
            entity_id=ENTITY_ID,
            character_start=0,
            character_end=8,
        ),
    )

    assert link.revision_id == revision_result.revision.id
    assert link.outline_node_id == NODE_ID
    assert link.character_start == 0
    assert link.character_end == 8


@pytest.mark.asyncio
async def test_passage_anchor_without_revision_is_rejected() -> None:
    repository = FakeWritingRepository()
    service = WritingStructureService(repository=repository)  # type: ignore[arg-type]

    with pytest.raises(WritingValidationError, match="require a manuscript revision"):
        await service.create_research_link(
            access_token="jwt",
            project_id=PROJECT_ID,
            document_id=DOCUMENT_ID,
            request=CreateWritingResearchLinkRequest(
                kind=WritingResearchLinkKind.CLAIM,
                entity_id=ENTITY_ID,
                character_start=0,
                character_end=5,
            ),
        )


@pytest.mark.asyncio
async def test_outline_cannot_be_its_own_parent() -> None:
    repository = FakeWritingRepository()
    service = WritingStructureService(repository=repository)  # type: ignore[arg-type]

    with pytest.raises(WritingValidationError, match="own parent"):
        await service.update_outline_node(
            access_token="jwt",
            project_id=PROJECT_ID,
            node_id=NODE_ID,
            request=UpdateOutlineNodeRequest(parent_id=NODE_ID),
        )


@pytest.mark.asyncio
async def test_workspace_summary_uses_current_document_word_counts() -> None:
    repository = FakeWritingRepository()
    service = WritingStructureService(repository=repository)  # type: ignore[arg-type]
    await service.create_revision(
        access_token="jwt",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        request=CreateManuscriptRevisionRequest(content="Five words live right here."),
    )

    summary = await service.workspace_summary(
        access_token="jwt",
        project_id=PROJECT_ID,
    )

    assert summary.outline_nodes == 1
    assert summary.manuscript_documents == 1
    assert summary.current_word_count == 5
    assert summary.research_links == 0
