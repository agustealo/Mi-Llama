from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import uvicorn

from mi_llama.config import Settings
from mi_llama.domain import Source, SourceChunk, SourceStatus
from mi_llama.research_structure.models import CreateResearchNoteRequest, ResearchNote
from mi_llama.workspace import create_app as create_workspace_app
from mi_llama.writing_studio.models import (
    ManuscriptDraft,
    WritingProposal,
    WritingProposalOperation,
    WritingProposalStatus,
)

try:
    from product_fixture_server import FixtureProvider, FixtureRepository, FixtureStorage, USER_ID
except ModuleNotFoundError:  # Imported as docs.product_fixture_strict_server in tests.
    from docs.product_fixture_server import FixtureProvider, FixtureRepository, FixtureStorage, USER_ID


class StrictFixtureProvider(FixtureProvider):
    async def chat_json(
        self,
        *,
        model: str,
        messages: Any,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        del model, schema
        selected = ""
        for message in reversed(list(messages)):
            content = getattr(message, "content", "")
            if "Selected passage:\n" in content:
                selected = content.split("Selected passage:\n", 1)[1].split("\n\nContext after:", 1)[0]
                break
        return {"replacement": selected.strip() or "Mi-Llama fixture revision"}


class StrictFixtureRepository(FixtureRepository):
    """Product-gallery repository that mirrors production readiness and writing-studio rules."""

    def __init__(self) -> None:
        super().__init__()
        self.manuscript_drafts: dict[UUID, ManuscriptDraft] = {}
        self.writing_proposals: dict[UUID, WritingProposal] = {}

    def _chunk_is_ready(self, chunk: SourceChunk) -> bool:
        version = self.source_versions.get(chunk.source_version_id)
        source = self.sources.get(chunk.source_id)
        return bool(
            version
            and source
            and version.source_id == chunk.source_id
            and version.project_id == chunk.project_id
            and source.project_id == chunk.project_id
            and version.status == SourceStatus.READY
            and source.status == SourceStatus.READY
        )

    async def find_source_by_checksum(
        self, *, access_token: str, project_id: UUID, checksum_sha256: str
    ) -> Source | None:
        self._check(access_token)
        return next(
            (
                source
                for source in self.sources.values()
                if source.project_id == project_id
                and source.checksum_sha256 == checksum_sha256
                and source.status == SourceStatus.READY
            ),
            None,
        )

    async def get_source_chunks(
        self, *, access_token: str, source_version_id: UUID
    ) -> list[SourceChunk]:
        self._check(access_token)
        version = self.source_versions.get(source_version_id)
        if version is None or version.status != SourceStatus.READY:
            return []
        source = self.sources.get(version.source_id)
        if source is None or source.status != SourceStatus.READY:
            return []
        return [
            chunk
            for chunk in self.source_chunks.values()
            if chunk.source_version_id == source_version_id and self._chunk_is_ready(chunk)
        ]

    async def get_research_chunk(
        self, *, access_token: str, project_id: UUID, chunk_id: UUID
    ) -> SourceChunk | None:
        self._check(access_token)
        chunk = self.source_chunks.get(chunk_id)
        if chunk is None or chunk.project_id != project_id or not self._chunk_is_ready(chunk):
            return None
        return chunk

    async def create_research_note(
        self,
        *,
        access_token: str,
        project_id: UUID,
        request: CreateResearchNoteRequest,
    ) -> ResearchNote:
        if request.source_chunk_id is not None:
            chunk = await self.get_research_chunk(
                access_token=access_token,
                project_id=project_id,
                chunk_id=request.source_chunk_id,
            )
            if chunk is None:
                raise ValueError(
                    "research note source chunk must be ready and belong to the same project"
                )
        return await super().create_research_note(
            access_token=access_token,
            project_id=project_id,
            request=request,
        )

    async def persist_writing_analysis(self, **kwargs: Any) -> Any:
        raise NotImplementedError("fixture evidence analysis is created only when explicitly exercised")

    async def list_writing_analysis_runs(self, **kwargs: Any) -> list[Any]:
        self._check(kwargs["access_token"])
        return []

    async def get_writing_analysis_run(self, **kwargs: Any) -> None:
        self._check(kwargs["access_token"])
        return None

    async def list_writing_analysis_findings(self, **kwargs: Any) -> list[Any]:
        self._check(kwargs["access_token"])
        return []

    async def list_writing_finding_candidates(self, **kwargs: Any) -> list[Any]:
        self._check(kwargs["access_token"])
        return []

    async def get_writing_analysis_finding(self, **kwargs: Any) -> None:
        self._check(kwargs["access_token"])
        return None

    async def review_writing_finding(self, **kwargs: Any) -> Any:
        raise KeyError(str(kwargs.get("finding_id")))

    async def promote_writing_finding_to_question(self, **kwargs: Any) -> Any:
        raise KeyError(str(kwargs.get("finding_id")))

    async def get_manuscript_draft(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
    ) -> ManuscriptDraft | None:
        self._check(access_token)
        document = self.documents.get(document_id)
        if document is None or document.project_id != project_id:
            return None
        return self.manuscript_drafts.get(document_id)

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
        self._check(access_token)
        now = datetime.now(UTC)
        draft = ManuscriptDraft(
            id=uuid4(),
            project_id=project_id,
            document_id=document_id,
            created_by=USER_ID,
            updated_by=USER_ID,
            base_revision_id=base_revision_id,
            version=1,
            editor_state=editor_state,
            plain_text=plain_text,
            created_at=now,
            updated_at=now,
        )
        self.manuscript_drafts[document_id] = draft
        return draft

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
        del base_revision_id
        self._check(access_token)
        draft = self.manuscript_drafts.get(document_id)
        if draft is None or draft.project_id != project_id or draft.version != expected_version:
            return None
        updated = draft.model_copy(
            update={
                "version": draft.version + 1,
                "updated_by": USER_ID,
                "editor_state": editor_state,
                "plain_text": plain_text,
                "updated_at": datetime.now(UTC),
            }
        )
        self.manuscript_drafts[document_id] = updated
        return updated

    async def checkpoint_manuscript_draft(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        expected_draft_version: int,
    ):
        self._check(access_token)
        draft = self.manuscript_drafts[document_id]
        if draft.project_id != project_id or draft.version != expected_draft_version:
            raise RuntimeError("manuscript draft version is stale")
        document = self.documents[document_id]
        existing = [
            item for item in self.revisions.values() if item.document_id == document_id
        ]
        revision = await super().create_manuscript_revision(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            content=draft.plain_text,
        )
        revision = revision.model_copy(
            update={
                "revision_number": len(existing) + 1,
                "editor_state": draft.editor_state,
            }
        )
        self.revisions[revision.id] = revision
        self.documents[document_id] = document.model_copy(
            update={
                "current_revision_id": revision.id,
                "current_word_count": revision.word_count,
                "updated_at": datetime.now(UTC),
            }
        )
        self.manuscript_drafts[document_id] = draft.model_copy(
            update={
                "base_revision_id": revision.id,
                "version": draft.version + 1,
                "updated_by": USER_ID,
                "updated_at": datetime.now(UTC),
            }
        )
        for proposal_id, proposal in list(self.writing_proposals.items()):
            if (
                proposal.document_id == document_id
                and proposal.status == WritingProposalStatus.PROPOSED
                and proposal.base_draft_version <= expected_draft_version
            ):
                self.writing_proposals[proposal_id] = proposal.model_copy(
                    update={"status": WritingProposalStatus.STALE, "updated_at": datetime.now(UTC)}
                )
        return revision

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
        self._check(access_token)
        now = datetime.now(UTC)
        proposal = WritingProposal(
            id=uuid4(),
            project_id=project_id,
            document_id=document_id,
            created_by=USER_ID,
            base_draft_version=base_draft_version,
            base_revision_id=base_revision_id,
            operation=operation,
            model=model,
            prompt=prompt,
            selection_start=selection_start,
            selection_end=selection_end,
            selection_hash=selection_hash,
            original_text=original_text,
            proposed_text=proposed_text,
            context_manifest=context_manifest,
            status=WritingProposalStatus.PROPOSED,
            created_at=now,
            updated_at=now,
        )
        self.writing_proposals[proposal.id] = proposal
        return proposal

    async def get_writing_proposal(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        proposal_id: UUID,
    ) -> WritingProposal | None:
        self._check(access_token)
        proposal = self.writing_proposals.get(proposal_id)
        if (
            proposal is None
            or proposal.project_id != project_id
            or proposal.document_id != document_id
        ):
            return None
        return proposal

    async def list_writing_proposals(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
    ) -> list[WritingProposal]:
        self._check(access_token)
        return sorted(
            [
                proposal
                for proposal in self.writing_proposals.values()
                if proposal.project_id == project_id and proposal.document_id == document_id
            ],
            key=lambda proposal: proposal.created_at,
            reverse=True,
        )

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
        self._check(access_token)
        draft = self.manuscript_drafts[document_id]
        proposal = self.writing_proposals[proposal_id]
        if draft.version != expected_draft_version:
            raise RuntimeError("manuscript draft version is stale")
        now = datetime.now(UTC)
        updated_draft = draft.model_copy(
            update={
                "version": draft.version + 1,
                "editor_state": editor_state,
                "plain_text": plain_text,
                "updated_by": USER_ID,
                "updated_at": now,
            }
        )
        self.manuscript_drafts[document_id] = updated_draft
        self.writing_proposals[proposal_id] = proposal.model_copy(
            update={
                "status": WritingProposalStatus.ACCEPTED,
                "reviewed_by": USER_ID,
                "reviewed_at": now,
                "updated_at": now,
            }
        )
        return updated_draft

    async def reject_writing_proposal(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        proposal_id: UUID,
    ) -> WritingProposal | None:
        proposal = await self.get_writing_proposal(
            access_token=access_token,
            project_id=project_id,
            document_id=document_id,
            proposal_id=proposal_id,
        )
        if proposal is None or proposal.status != WritingProposalStatus.PROPOSED:
            return None
        now = datetime.now(UTC)
        rejected = proposal.model_copy(
            update={
                "status": WritingProposalStatus.REJECTED,
                "reviewed_by": USER_ID,
                "reviewed_at": now,
                "updated_at": now,
            }
        )
        self.writing_proposals[proposal_id] = rejected
        return rejected


def build_app():
    settings = Settings(
        _env_file=None,
        supabase_url="https://fixture.invalid",
        supabase_publishable_key="fixture-public-key",
        mindsdb_enabled=False,
    )
    return create_workspace_app(
        settings=settings,
        provider=StrictFixtureProvider(),
        repository=StrictFixtureRepository(),
        storage=FixtureStorage(),
        research_engine=None,
    )


if __name__ == "__main__":
    uvicorn.run(build_app(), host="127.0.0.1", port=8765, log_level="info")
