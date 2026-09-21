from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from mi_llama.research_structure.repository import SupabaseResearchRepository
from mi_llama.writing_structure.models import (
    ManuscriptDocument,
    ManuscriptRevision,
    OutlineNode,
    OutlineNodeKind,
    WritingResearchLink,
    WritingResearchLinkKind,
)


@runtime_checkable
class WritingRepository(Protocol):
    async def create_outline_node(
        self,
        *,
        access_token: str,
        project_id: UUID,
        parent_id: UUID | None,
        kind: OutlineNodeKind,
        title: str,
        summary: str | None,
        position: int,
    ) -> OutlineNode: ...

    async def list_outline_nodes(
        self,
        *,
        access_token: str,
        project_id: UUID,
    ) -> list[OutlineNode]: ...

    async def get_outline_node(
        self,
        *,
        access_token: str,
        project_id: UUID,
        node_id: UUID,
    ) -> OutlineNode | None: ...

    async def update_outline_node(
        self,
        *,
        access_token: str,
        project_id: UUID,
        node_id: UUID,
        changes: dict[str, Any],
    ) -> OutlineNode: ...

    async def create_manuscript_document(
        self,
        *,
        access_token: str,
        project_id: UUID,
        outline_node_id: UUID | None,
        title: str,
    ) -> ManuscriptDocument: ...

    async def list_manuscript_documents(
        self,
        *,
        access_token: str,
        project_id: UUID,
    ) -> list[ManuscriptDocument]: ...

    async def get_manuscript_document(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
    ) -> ManuscriptDocument | None: ...

    async def update_manuscript_document(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        changes: dict[str, Any],
    ) -> ManuscriptDocument: ...

    async def create_manuscript_revision(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        content: str,
    ) -> ManuscriptRevision: ...

    async def list_manuscript_revisions(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
    ) -> list[ManuscriptRevision]: ...

    async def get_manuscript_revision(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        revision_id: UUID,
    ) -> ManuscriptRevision | None: ...

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
    ) -> WritingResearchLink: ...

    async def list_writing_research_links(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID | None = None,
    ) -> list[WritingResearchLink]: ...


class SupabaseWritingRepository(SupabaseResearchRepository):
    """Canonical Supabase repository extended with writing workspace state."""

    async def create_outline_node(
        self,
        *,
        access_token: str,
        project_id: UUID,
        parent_id: UUID | None,
        kind: OutlineNodeKind,
        title: str,
        summary: str | None,
        position: int,
    ) -> OutlineNode:
        rows = await self._request_rows(
            "POST",
            "/outline_nodes",
            access_token=access_token,
            json={
                "project_id": str(project_id),
                "parent_id": None if parent_id is None else str(parent_id),
                "kind": kind.value,
                "title": title,
                "summary": summary,
                "position": position,
            },
            prefer="return=representation",
        )
        return self._one(rows, OutlineNode)

    async def list_outline_nodes(
        self,
        *,
        access_token: str,
        project_id: UUID,
    ) -> list[OutlineNode]:
        rows = await self._request_rows(
            "GET",
            "/outline_nodes",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "order": "position.asc,created_at.asc",
            },
        )
        return self._many(rows, OutlineNode)

    async def get_outline_node(
        self,
        *,
        access_token: str,
        project_id: UUID,
        node_id: UUID,
    ) -> OutlineNode | None:
        rows = await self._request_rows(
            "GET",
            "/outline_nodes",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "id": f"eq.{node_id}",
                "limit": "1",
            },
        )
        return None if not rows else self._one(rows, OutlineNode)

    async def update_outline_node(
        self,
        *,
        access_token: str,
        project_id: UUID,
        node_id: UUID,
        changes: dict[str, Any],
    ) -> OutlineNode:
        rows = await self._request_rows(
            "PATCH",
            "/outline_nodes",
            access_token=access_token,
            params={"project_id": f"eq.{project_id}", "id": f"eq.{node_id}"},
            json=changes,
            prefer="return=representation",
        )
        return self._one(rows, OutlineNode)

    async def create_manuscript_document(
        self,
        *,
        access_token: str,
        project_id: UUID,
        outline_node_id: UUID | None,
        title: str,
    ) -> ManuscriptDocument:
        rows = await self._request_rows(
            "POST",
            "/manuscript_documents",
            access_token=access_token,
            json={
                "project_id": str(project_id),
                "outline_node_id": (
                    None if outline_node_id is None else str(outline_node_id)
                ),
                "title": title,
            },
            prefer="return=representation",
        )
        return self._one(rows, ManuscriptDocument)

    async def list_manuscript_documents(
        self,
        *,
        access_token: str,
        project_id: UUID,
    ) -> list[ManuscriptDocument]:
        rows = await self._request_rows(
            "GET",
            "/manuscript_documents",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "order": "updated_at.desc",
            },
        )
        return self._many(rows, ManuscriptDocument)

    async def get_manuscript_document(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
    ) -> ManuscriptDocument | None:
        rows = await self._request_rows(
            "GET",
            "/manuscript_documents",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "id": f"eq.{document_id}",
                "limit": "1",
            },
        )
        return None if not rows else self._one(rows, ManuscriptDocument)

    async def update_manuscript_document(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        changes: dict[str, Any],
    ) -> ManuscriptDocument:
        rows = await self._request_rows(
            "PATCH",
            "/manuscript_documents",
            access_token=access_token,
            params={
                "project_id": f"eq.{project_id}",
                "id": f"eq.{document_id}",
            },
            json=changes,
            prefer="return=representation",
        )
        return self._one(rows, ManuscriptDocument)

    async def create_manuscript_revision(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        content: str,
    ) -> ManuscriptRevision:
        rows = await self._request_rows(
            "POST",
            "/rpc/create_manuscript_revision",
            access_token=access_token,
            json={
                "p_project_id": str(project_id),
                "p_document_id": str(document_id),
                "p_content": content,
            },
        )
        return self._one(rows, ManuscriptRevision)

    async def list_manuscript_revisions(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
    ) -> list[ManuscriptRevision]:
        rows = await self._request_rows(
            "GET",
            "/manuscript_revisions",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "document_id": f"eq.{document_id}",
                "order": "revision_number.desc",
            },
        )
        return self._many(rows, ManuscriptRevision)

    async def get_manuscript_revision(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        revision_id: UUID,
    ) -> ManuscriptRevision | None:
        rows = await self._request_rows(
            "GET",
            "/manuscript_revisions",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "document_id": f"eq.{document_id}",
                "id": f"eq.{revision_id}",
                "limit": "1",
            },
        )
        return None if not rows else self._one(rows, ManuscriptRevision)

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
        rows = await self._request_rows(
            "POST",
            "/writing_research_links",
            access_token=access_token,
            json={
                "project_id": str(project_id),
                "document_id": str(document_id),
                "outline_node_id": (
                    None if outline_node_id is None else str(outline_node_id)
                ),
                "revision_id": None if revision_id is None else str(revision_id),
                "kind": kind.value,
                "entity_id": str(entity_id),
                "character_start": character_start,
                "character_end": character_end,
            },
            prefer="return=representation",
        )
        return self._one(rows, WritingResearchLink)

    async def list_writing_research_links(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID | None = None,
    ) -> list[WritingResearchLink]:
        params = {
            "select": "*",
            "project_id": f"eq.{project_id}",
            "order": "created_at.asc",
        }
        if document_id is not None:
            params["document_id"] = f"eq.{document_id}"
        rows = await self._request_rows(
            "GET",
            "/writing_research_links",
            access_token=access_token,
            params=params,
        )
        return self._many(rows, WritingResearchLink)
