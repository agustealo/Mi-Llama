from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from mi_llama.domain import Conversation, ManuscriptMessageContext, Role, StoredMessage
from mi_llama.repositories import Repository
from mi_llama.writing_intelligence.repository import (
    SupabaseWritingIntelligenceRepository,
    WritingIntelligenceRepository,
)
from mi_llama.writing_structure.models import ManuscriptRevision
from mi_llama.writing_studio.models import (
    ManuscriptDraft,
    WritingProposal,
    WritingProposalOperation,
    WritingProposalStatus,
)


@runtime_checkable
class WritingStudioRepository(WritingIntelligenceRepository, Repository, Protocol):
    async def get_manuscript_draft(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
    ) -> ManuscriptDraft | None: ...

    async def create_manuscript_draft(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        base_revision_id: UUID | None,
        editor_state: dict[str, Any],
        plain_text: str,
    ) -> ManuscriptDraft: ...

    async def update_manuscript_draft(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        expected_version: int,
        base_revision_id: UUID | None,
        editor_state: dict[str, Any],
        plain_text: str,
    ) -> ManuscriptDraft | None: ...

    async def checkpoint_manuscript_draft(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        expected_draft_version: int,
    ) -> ManuscriptRevision: ...

    async def create_writing_proposal(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        base_draft_version: int,
        base_revision_id: UUID | None,
        operation: WritingProposalOperation,
        model: str,
        prompt: str | None,
        selection_start: int,
        selection_end: int,
        selection_hash: str,
        original_text: str,
        proposed_text: str,
        context_manifest: dict[str, Any],
    ) -> WritingProposal: ...

    async def get_writing_proposal(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        proposal_id: UUID,
    ) -> WritingProposal | None: ...

    async def list_writing_proposals(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
    ) -> list[WritingProposal]: ...

    async def apply_writing_proposal(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        proposal_id: UUID,
        expected_draft_version: int,
        editor_state: dict[str, Any],
        plain_text: str,
    ) -> ManuscriptDraft: ...

    async def reject_writing_proposal(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        proposal_id: UUID,
    ) -> WritingProposal | None: ...


class SupabaseWritingStudioRepository(SupabaseWritingIntelligenceRepository):
    """Supabase repository extended with mutable draft and AI proposal authority."""

    async def list_conversations(
        self, *, access_token: str, project_id: UUID
    ) -> list[Conversation]:
        rows = await self._request_rows(
            "GET",
            "/conversation_activity",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "order": "activity_at.desc,created_at.desc",
            },
        )
        return self._many(rows, Conversation)

    async def create_document_conversation(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        model: str,
        title: str | None,
    ) -> Conversation:
        rows = await self._request_rows(
            "POST",
            "/conversations",
            access_token=access_token,
            json={
                "project_id": str(project_id),
                "document_id": str(document_id),
                "model": model,
                "title": (title or "New conversation").strip() or "New conversation",
            },
            prefer="return=representation",
        )
        return self._one(rows, Conversation)

    async def add_context_message(
        self,
        *,
        access_token: str,
        conversation_id: UUID,
        role: Role,
        content: str,
        context: ManuscriptMessageContext,
    ) -> StoredMessage:
        rows = await self._request_rows(
            "POST",
            "/messages",
            access_token=access_token,
            json={
                "conversation_id": str(conversation_id),
                "role": role.value,
                "content": content,
                "context": context.model_dump(mode="json"),
            },
            prefer="return=representation",
        )
        return self._one(rows, StoredMessage)

    async def get_manuscript_draft(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
    ) -> ManuscriptDraft | None:
        rows = await self._request_rows(
            "GET",
            "/manuscript_drafts",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "document_id": f"eq.{document_id}",
                "limit": "1",
            },
        )
        return None if not rows else self._one(rows, ManuscriptDraft)

    async def create_manuscript_draft(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        base_revision_id: UUID | None,
        editor_state: dict[str, Any],
        plain_text: str,
    ) -> ManuscriptDraft:
        rows = await self._request_rows(
            "POST",
            "/manuscript_drafts",
            access_token=access_token,
            json={
                "project_id": str(project_id),
                "document_id": str(document_id),
                "base_revision_id": None if base_revision_id is None else str(base_revision_id),
                "editor_state": editor_state,
                "plain_text": plain_text,
            },
            prefer="return=representation",
        )
        return self._one(rows, ManuscriptDraft)

    async def update_manuscript_draft(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        expected_version: int,
        base_revision_id: UUID | None,
        editor_state: dict[str, Any],
        plain_text: str,
    ) -> ManuscriptDraft | None:
        # Ordinary autosave is not allowed to move revision authority. Only the
        # checkpoint/evidence/citation transactions may advance base_revision_id.
        del base_revision_id
        rows = await self._request_rows(
            "PATCH",
            "/manuscript_drafts",
            access_token=access_token,
            params={
                "project_id": f"eq.{project_id}",
                "document_id": f"eq.{document_id}",
                "version": f"eq.{expected_version}",
            },
            json={
                "editor_state": editor_state,
                "plain_text": plain_text,
                "version": expected_version + 1,
            },
            prefer="return=representation",
        )
        return None if not rows else self._one(rows, ManuscriptDraft)

    async def checkpoint_manuscript_draft(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        expected_draft_version: int,
    ) -> ManuscriptRevision:
        rows = await self._request_rows(
            "POST",
            "/rpc/checkpoint_manuscript_draft",
            access_token=access_token,
            json={
                "p_project_id": str(project_id),
                "p_document_id": str(document_id),
                "p_expected_draft_version": expected_draft_version,
            },
        )
        return self._one(rows, ManuscriptRevision)

    async def create_writing_proposal(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        base_draft_version: int,
        base_revision_id: UUID | None,
        operation: WritingProposalOperation,
        model: str,
        prompt: str | None,
        selection_start: int,
        selection_end: int,
        selection_hash: str,
        original_text: str,
        proposed_text: str,
        context_manifest: dict[str, Any],
    ) -> WritingProposal:
        rows = await self._request_rows(
            "POST",
            "/writing_proposals",
            access_token=access_token,
            json={
                "project_id": str(project_id),
                "document_id": str(document_id),
                "base_draft_version": base_draft_version,
                "base_revision_id": None if base_revision_id is None else str(base_revision_id),
                "operation": operation.value,
                "model": model,
                "prompt": prompt,
                "selection_start": selection_start,
                "selection_end": selection_end,
                "selection_hash": selection_hash,
                "original_text": original_text,
                "proposed_text": proposed_text,
                "context_manifest": context_manifest,
            },
            prefer="return=representation",
        )
        return self._one(rows, WritingProposal)

    async def get_writing_proposal(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        proposal_id: UUID,
    ) -> WritingProposal | None:
        rows = await self._request_rows(
            "GET",
            "/writing_proposals",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "document_id": f"eq.{document_id}",
                "id": f"eq.{proposal_id}",
                "limit": "1",
            },
        )
        return None if not rows else self._one(rows, WritingProposal)

    async def list_writing_proposals(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
    ) -> list[WritingProposal]:
        rows = await self._request_rows(
            "GET",
            "/writing_proposals",
            access_token=access_token,
            params={
                "select": "*",
                "project_id": f"eq.{project_id}",
                "document_id": f"eq.{document_id}",
                "order": "created_at.desc",
            },
        )
        return self._many(rows, WritingProposal)

    async def apply_writing_proposal(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        proposal_id: UUID,
        expected_draft_version: int,
        editor_state: dict[str, Any],
        plain_text: str,
    ) -> ManuscriptDraft:
        rows = await self._request_rows(
            "POST",
            "/rpc/apply_writing_proposal",
            access_token=access_token,
            json={
                "p_project_id": str(project_id),
                "p_document_id": str(document_id),
                "p_proposal_id": str(proposal_id),
                "p_expected_draft_version": expected_draft_version,
                "p_editor_state": editor_state,
                "p_plain_text": plain_text,
            },
        )
        return self._one(rows, ManuscriptDraft)

    async def reject_writing_proposal(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        proposal_id: UUID,
    ) -> WritingProposal | None:
        rows = await self._request_rows(
            "PATCH",
            "/writing_proposals",
            access_token=access_token,
            params={
                "project_id": f"eq.{project_id}",
                "document_id": f"eq.{document_id}",
                "id": f"eq.{proposal_id}",
                "status": f"eq.{WritingProposalStatus.PROPOSED.value}",
            },
            json={"status": WritingProposalStatus.REJECTED.value},
            prefer="return=representation",
        )
        return None if not rows else self._one(rows, WritingProposal)
