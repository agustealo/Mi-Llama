from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from mi_llama.domain import LearningEvent
from mi_llama.writing_structure import ManuscriptDocument, ManuscriptStatus
from mi_llama.writing_studio import (
    ApplyWritingProposalRequest,
    CreateWritingProposalRequest,
    DraftVersionConflict,
    ManuscriptDraft,
    RefineWritingProposalRequest,
    SaveManuscriptDraftRequest,
    WritingProposal,
    WritingProposalOperation,
    WritingProposalStale,
    WritingProposalStatus,
    WritingStudioService,
)
from mi_llama.writing_studio.proposal_iteration import ProposalIterationService

PROJECT_ID = UUID("11111111-1111-1111-1111-111111111111")
USER_ID = UUID("22222222-2222-2222-2222-222222222222")
DOCUMENT_ID = UUID("33333333-3333-3333-3333-333333333333")


def _now() -> datetime:
    return datetime.now(UTC)


class FakeStructuredProvider:
    async def chat_json(
        self,
        *,
        model: str,
        messages: Any,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        del model
        if "explanation" in schema.get("properties", {}):
            return {
                "explanation": (
                    "The proposal tightens the wording while preserving the original claim."
                )
            }
        last_content = messages[-1].content if messages else ""
        if "Existing proposal:" in last_content:
            return {"replacement": "The refined passage is tighter."}
        return {"replacement": "The revised passage is clearer."}


class FakeWritingStudioRepository:
    def __init__(self) -> None:
        now = _now()
        self.document = ManuscriptDocument(
            id=DOCUMENT_ID,
            project_id=PROJECT_ID,
            outline_node_id=None,
            created_by=USER_ID,
            title="Chapter One",
            status=ManuscriptStatus.DRAFTING,
            current_revision_id=None,
            current_word_count=0,
            created_at=now,
            updated_at=now,
        )
        self.draft: ManuscriptDraft | None = None
        self.proposals: dict[UUID, WritingProposal] = {}
        self.learning_events: list[LearningEvent] = []

    async def get_manuscript_document(
        self, *, access_token: str, project_id: UUID, document_id: UUID
    ) -> ManuscriptDocument | None:
        del access_token
        if project_id == PROJECT_ID and document_id == DOCUMENT_ID:
            return self.document
        return None

    async def get_manuscript_revision(self, **kwargs: Any) -> None:
        del kwargs
        return None

    async def get_manuscript_draft(
        self, *, access_token: str, project_id: UUID, document_id: UUID
    ) -> ManuscriptDraft | None:
        del access_token
        if project_id == PROJECT_ID and document_id == DOCUMENT_ID:
            return self.draft
        return None

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
        del access_token
        now = _now()
        self.draft = ManuscriptDraft(
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
        return self.draft

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
        del access_token, project_id, document_id
        if self.draft is None or self.draft.version != expected_version:
            return None
        self.draft = self.draft.model_copy(
            update={
                "base_revision_id": base_revision_id,
                "version": expected_version + 1,
                "editor_state": editor_state,
                "plain_text": plain_text,
                "updated_at": _now(),
            }
        )
        return self.draft

    async def create_writing_proposal(self, **kwargs: Any) -> WritingProposal:
        now = _now()
        proposal = WritingProposal(
            id=uuid4(),
            project_id=kwargs["project_id"],
            document_id=kwargs["document_id"],
            created_by=USER_ID,
            base_draft_version=kwargs["base_draft_version"],
            base_revision_id=kwargs["base_revision_id"],
            operation=kwargs["operation"],
            model=kwargs["model"],
            prompt=kwargs["prompt"],
            selection_start=kwargs["selection_start"],
            selection_end=kwargs["selection_end"],
            selection_hash=kwargs["selection_hash"],
            original_text=kwargs["original_text"],
            proposed_text=kwargs["proposed_text"],
            context_manifest=kwargs["context_manifest"],
            status=WritingProposalStatus.PROPOSED,
            created_at=now,
            updated_at=now,
        )
        self.proposals[proposal.id] = proposal
        return proposal

    async def get_writing_proposal(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        proposal_id: UUID,
    ) -> WritingProposal | None:
        del access_token
        proposal = self.proposals.get(proposal_id)
        if (
            proposal is not None
            and proposal.project_id == project_id
            and proposal.document_id == document_id
        ):
            return proposal
        return None

    async def list_writing_proposals(
        self, *, access_token: str, project_id: UUID, document_id: UUID
    ) -> list[WritingProposal]:
        del access_token
        return [
            proposal
            for proposal in self.proposals.values()
            if proposal.project_id == project_id and proposal.document_id == document_id
        ]

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
        del access_token, project_id, document_id
        assert self.draft is not None
        assert self.draft.version == expected_draft_version
        proposal = self.proposals[proposal_id]
        assert proposal.status is WritingProposalStatus.PROPOSED
        self.draft = self.draft.model_copy(
            update={
                "version": expected_draft_version + 1,
                "editor_state": editor_state,
                "plain_text": plain_text,
                "updated_at": _now(),
            }
        )
        self.proposals[proposal_id] = proposal.model_copy(
            update={
                "status": WritingProposalStatus.ACCEPTED,
                "reviewed_by": USER_ID,
                "reviewed_at": _now(),
                "updated_at": _now(),
            }
        )
        return self.draft

    async def reject_writing_proposal(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        proposal_id: UUID,
    ) -> WritingProposal | None:
        del access_token, project_id, document_id
        proposal = self.proposals.get(proposal_id)
        if proposal is None or proposal.status is not WritingProposalStatus.PROPOSED:
            return None
        rejected = proposal.model_copy(
            update={
                "status": WritingProposalStatus.REJECTED,
                "reviewed_by": USER_ID,
                "reviewed_at": _now(),
                "updated_at": _now(),
            }
        )
        self.proposals[proposal_id] = rejected
        return rejected

    async def add_learning_signal(self, *, event_type: LearningEvent, **kwargs: Any) -> Any:
        del kwargs
        self.learning_events.append(event_type)
        return None


async def _seed_draft(
    service: WritingStudioService,
    text: str = "This sentence needs work. The next sentence stays.",
) -> ManuscriptDraft:
    return await service.save_draft(
        access_token="jwt",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        request=SaveManuscriptDraftRequest(
            expected_version=None,
            editor_state={"schema": "plain_text_v1", "text": text},
            plain_text=text,
        ),
    )


@pytest.mark.asyncio
async def test_draft_autosave_uses_optimistic_versioning() -> None:
    repository = FakeWritingStudioRepository()
    service = WritingStudioService(
        repository=repository,  # type: ignore[arg-type]
        provider=FakeStructuredProvider(),  # type: ignore[arg-type]
    )
    draft = await _seed_draft(service)

    updated = await service.save_draft(
        access_token="jwt",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        request=SaveManuscriptDraftRequest(
            expected_version=draft.version,
            editor_state={"schema": "plain_text_v1", "text": "Updated"},
            plain_text="Updated",
        ),
    )

    assert updated.version == 2
    with pytest.raises(DraftVersionConflict):
        await service.save_draft(
            access_token="jwt",
            project_id=PROJECT_ID,
            document_id=DOCUMENT_ID,
            request=SaveManuscriptDraftRequest(
                expected_version=1,
                editor_state={"schema": "plain_text_v1", "text": "Stale"},
                plain_text="Stale",
            ),
        )


@pytest.mark.asyncio
async def test_proposal_is_bound_to_exact_selection_and_draft_version() -> None:
    repository = FakeWritingStudioRepository()
    service = WritingStudioService(
        repository=repository,  # type: ignore[arg-type]
        provider=FakeStructuredProvider(),  # type: ignore[arg-type]
    )
    draft = await _seed_draft(service)

    proposal = await service.create_proposal(
        access_token="jwt",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        request=CreateWritingProposalRequest(
            expected_draft_version=draft.version,
            operation=WritingProposalOperation.IMPROVE,
            model="llama-test",
            selection_start=0,
            selection_end=25,
        ),
    )

    assert proposal.original_text == "This sentence needs work."
    assert proposal.proposed_text == "The revised passage is clearer."
    assert proposal.base_draft_version == 1
    assert len(proposal.selection_hash) == 64


@pytest.mark.asyncio
async def test_accept_proposal_applies_only_reviewed_range_and_records_provenance() -> None:
    repository = FakeWritingStudioRepository()
    service = WritingStudioService(
        repository=repository,  # type: ignore[arg-type]
        provider=FakeStructuredProvider(),  # type: ignore[arg-type]
    )
    draft = await _seed_draft(service)
    proposal = await service.create_proposal(
        access_token="jwt",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        request=CreateWritingProposalRequest(
            expected_draft_version=draft.version,
            operation=WritingProposalOperation.IMPROVE,
            model="llama-test",
            selection_start=0,
            selection_end=25,
        ),
    )

    result = await service.accept_proposal(
        access_token="jwt",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        proposal_id=proposal.id,
        request=ApplyWritingProposalRequest(expected_draft_version=draft.version),
    )

    assert result.draft.version == 2
    assert result.draft.plain_text == "The revised passage is clearer. The next sentence stays."
    assert result.proposal.status is WritingProposalStatus.ACCEPTED
    assert repository.learning_events == [LearningEvent.AI_EDIT_ACCEPTED]


@pytest.mark.asyncio
async def test_proposal_becomes_stale_when_draft_advances() -> None:
    repository = FakeWritingStudioRepository()
    service = WritingStudioService(
        repository=repository,  # type: ignore[arg-type]
        provider=FakeStructuredProvider(),  # type: ignore[arg-type]
    )
    draft = await _seed_draft(service)
    proposal = await service.create_proposal(
        access_token="jwt",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        request=CreateWritingProposalRequest(
            expected_draft_version=draft.version,
            operation=WritingProposalOperation.REWRITE,
            model="llama-test",
            selection_start=0,
            selection_end=25,
        ),
    )
    await service.save_draft(
        access_token="jwt",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        request=SaveManuscriptDraftRequest(
            expected_version=draft.version,
            editor_state={"schema": "plain_text_v1", "text": draft.plain_text + " More."},
            plain_text=draft.plain_text + " More.",
        ),
    )

    with pytest.raises(WritingProposalStale, match="changed"):
        await service.accept_proposal(
            access_token="jwt",
            project_id=PROJECT_ID,
            document_id=DOCUMENT_ID,
            proposal_id=proposal.id,
            request=ApplyWritingProposalRequest(expected_draft_version=draft.version),
        )


@pytest.mark.asyncio
async def test_reject_proposal_records_learning_signal_without_mutating_draft() -> None:
    repository = FakeWritingStudioRepository()
    service = WritingStudioService(
        repository=repository,  # type: ignore[arg-type]
        provider=FakeStructuredProvider(),  # type: ignore[arg-type]
    )
    draft = await _seed_draft(service)
    proposal = await service.create_proposal(
        access_token="jwt",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        request=CreateWritingProposalRequest(
            expected_draft_version=draft.version,
            operation=WritingProposalOperation.CONDENSE,
            model="llama-test",
            selection_start=0,
            selection_end=25,
        ),
    )

    rejected = await service.reject_proposal(
        access_token="jwt",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        proposal_id=proposal.id,
    )

    assert rejected.status is WritingProposalStatus.REJECTED
    assert repository.draft is not None and repository.draft.version == 1
    assert repository.learning_events == [LearningEvent.AI_EDIT_REJECTED]


@pytest.mark.asyncio
async def test_refinement_creates_immutable_child_lineage_without_mutating_draft() -> None:
    repository = FakeWritingStudioRepository()
    provider = FakeStructuredProvider()
    service = WritingStudioService(
        repository=repository,  # type: ignore[arg-type]
        provider=provider,  # type: ignore[arg-type]
    )
    iteration = ProposalIterationService(
        repository=repository,  # type: ignore[arg-type]
        provider=provider,  # type: ignore[arg-type]
    )
    draft = await _seed_draft(service)
    parent = await service.create_proposal(
        access_token="jwt",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        request=CreateWritingProposalRequest(
            expected_draft_version=draft.version,
            operation=WritingProposalOperation.IMPROVE,
            model="llama-test",
            selection_start=0,
            selection_end=25,
        ),
    )

    child = await iteration.refine(
        access_token="jwt",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        proposal_id=parent.id,
        request=RefineWritingProposalRequest(instruction="Make the rhythm less formal"),
    )

    assert child.id != parent.id
    assert child.proposed_text == "The refined passage is tighter."
    assert child.original_text == parent.original_text
    assert child.selection_hash == parent.selection_hash
    assert child.base_draft_version == parent.base_draft_version
    assert child.context_manifest["parent_proposal_id"] == str(parent.id)
    assert child.context_manifest["refinement_root_proposal_id"] == str(parent.id)
    assert child.context_manifest["refinement_depth"] == 1
    assert parent.status is WritingProposalStatus.PROPOSED
    assert repository.draft is not None and repository.draft.version == 1

    result = await service.accept_proposal(
        access_token="jwt",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        proposal_id=child.id,
        request=ApplyWritingProposalRequest(expected_draft_version=draft.version),
    )
    assert result.draft.plain_text == "The refined passage is tighter. The next sentence stays."


@pytest.mark.asyncio
async def test_explanation_is_read_only_review_metadata() -> None:
    repository = FakeWritingStudioRepository()
    provider = FakeStructuredProvider()
    service = WritingStudioService(
        repository=repository,  # type: ignore[arg-type]
        provider=provider,  # type: ignore[arg-type]
    )
    iteration = ProposalIterationService(
        repository=repository,  # type: ignore[arg-type]
        provider=provider,  # type: ignore[arg-type]
    )
    draft = await _seed_draft(service)
    proposal = await service.create_proposal(
        access_token="jwt",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        request=CreateWritingProposalRequest(
            expected_draft_version=draft.version,
            operation=WritingProposalOperation.REWRITE,
            model="llama-test",
            selection_start=0,
            selection_end=25,
        ),
    )

    explanation = await iteration.explain(
        access_token="jwt",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        proposal_id=proposal.id,
    )

    assert explanation.proposal_id == proposal.id
    assert explanation.model == proposal.model
    assert "tightens" in explanation.explanation
    assert repository.proposals[proposal.id].status is WritingProposalStatus.PROPOSED
    assert repository.draft is not None and repository.draft.version == draft.version
