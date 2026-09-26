from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from mi_llama.domain import LearningEvent
from mi_llama.structured_writing import (
    ApplyStructuredWritingProposalRequest,
    StructuredWritingService,
)
from mi_llama.writing_studio.models import (
    ManuscriptDraft,
    WritingProposal,
    WritingProposalOperation,
    WritingProposalStatus,
)
from mi_llama.writing_studio.service import WritingProposalStale, WritingStudioValidationError

PROJECT_ID = UUID("11111111-1111-4111-8111-111111111111")
DOCUMENT_ID = UUID("22222222-2222-4222-8222-222222222222")
USER_ID = UUID("33333333-3333-4333-8333-333333333333")
PROPOSAL_ID = UUID("44444444-4444-4444-8444-444444444444")


def _now() -> datetime:
    return datetime.now(UTC)


def _state(text: str) -> dict[str, Any]:
    return {
        "schema": "tiptap_v1",
        "doc": {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": text}],
                }
            ],
        },
    }


class FakeStructuredWritingRepository:
    def __init__(self) -> None:
        now = _now()
        original = "Alpha beta."
        self.draft = ManuscriptDraft(
            id=uuid4(),
            project_id=PROJECT_ID,
            document_id=DOCUMENT_ID,
            created_by=USER_ID,
            updated_by=USER_ID,
            version=7,
            editor_state=_state(original),
            plain_text=original,
            created_at=now,
            updated_at=now,
        )
        self.proposal = WritingProposal(
            id=PROPOSAL_ID,
            project_id=PROJECT_ID,
            document_id=DOCUMENT_ID,
            created_by=USER_ID,
            base_draft_version=7,
            operation=WritingProposalOperation.REWRITE,
            model="llama-test",
            selection_start=0,
            selection_end=5,
            selection_hash=hashlib.sha256(b"Alpha").hexdigest(),
            original_text="Alpha",
            proposed_text="Gamma",
            context_manifest={},
            status=WritingProposalStatus.PROPOSED,
            created_at=now,
            updated_at=now,
        )
        self.learning_events: list[tuple[LearningEvent, dict[str, Any]]] = []
        self.applied_editor_state: dict[str, Any] | None = None

    async def get_manuscript_draft(self, **kwargs: Any) -> ManuscriptDraft:
        del kwargs
        return self.draft

    async def get_writing_proposal(self, **kwargs: Any) -> WritingProposal | None:
        if kwargs["proposal_id"] != self.proposal.id:
            return None
        return self.proposal

    async def apply_writing_proposal(
        self,
        *,
        expected_draft_version: int,
        editor_state: dict[str, Any],
        plain_text: str,
        **kwargs: Any,
    ) -> ManuscriptDraft:
        del kwargs
        assert expected_draft_version == self.draft.version
        self.applied_editor_state = editor_state
        self.draft = self.draft.model_copy(
            update={
                "version": self.draft.version + 1,
                "editor_state": editor_state,
                "plain_text": plain_text,
                "updated_at": _now(),
            }
        )
        self.proposal = self.proposal.model_copy(
            update={
                "status": WritingProposalStatus.ACCEPTED,
                "reviewed_by": USER_ID,
                "reviewed_at": _now(),
                "updated_at": _now(),
            }
        )
        return self.draft

    async def add_learning_signal(
        self, *, event_type: LearningEvent, metadata: dict[str, Any], **kwargs: Any
    ) -> None:
        del kwargs
        self.learning_events.append((event_type, metadata))


@pytest.mark.asyncio
async def test_structured_acceptance_preserves_tiptap_state() -> None:
    repository = FakeStructuredWritingRepository()
    service = StructuredWritingService(repository=repository)  # type: ignore[arg-type]

    result = await service.accept_proposal(
        access_token="jwt",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        proposal_id=PROPOSAL_ID,
        request=ApplyStructuredWritingProposalRequest(
            expected_draft_version=7,
            editor_state=_state("Gamma beta."),
            plain_text="Gamma beta.",
        ),
    )

    assert result.draft.version == 8
    assert result.draft.plain_text == "Gamma beta."
    assert result.draft.editor_state["schema"] == "tiptap_v1"
    assert repository.applied_editor_state == _state("Gamma beta.")
    assert result.proposal.status is WritingProposalStatus.ACCEPTED
    assert repository.learning_events == [
        (
            LearningEvent.AI_EDIT_ACCEPTED,
            {
                "operation": "rewrite",
                "model": "llama-test",
                "base_draft_version": 7,
                "applied_draft_version": 8,
                "editor_schema": "tiptap_v1",
            },
        )
    ]


def test_structured_acceptance_request_rejects_projection_mismatch() -> None:
    with pytest.raises(ValidationError, match="projection does not match"):
        ApplyStructuredWritingProposalRequest(
            expected_draft_version=7,
            editor_state=_state("Wrong beta."),
            plain_text="Gamma beta.",
        )


@pytest.mark.asyncio
async def test_structured_acceptance_rejects_unreviewed_text_change() -> None:
    repository = FakeStructuredWritingRepository()
    service = StructuredWritingService(repository=repository)  # type: ignore[arg-type]

    with pytest.raises(WritingStudioValidationError, match="reviewed replacement"):
        await service.accept_proposal(
            access_token="jwt",
            project_id=PROJECT_ID,
            document_id=DOCUMENT_ID,
            proposal_id=PROPOSAL_ID,
            request=ApplyStructuredWritingProposalRequest(
                expected_draft_version=7,
                editor_state=_state("Gamma beta!"),
                plain_text="Gamma beta!",
            ),
        )

    assert repository.draft.version == 7
    assert repository.proposal.status is WritingProposalStatus.PROPOSED


@pytest.mark.asyncio
async def test_structured_acceptance_rejects_stale_draft_version() -> None:
    repository = FakeStructuredWritingRepository()
    service = StructuredWritingService(repository=repository)  # type: ignore[arg-type]

    with pytest.raises(WritingProposalStale, match="changed"):
        await service.accept_proposal(
            access_token="jwt",
            project_id=PROJECT_ID,
            document_id=DOCUMENT_ID,
            proposal_id=PROPOSAL_ID,
            request=ApplyStructuredWritingProposalRequest(
                expected_draft_version=6,
                editor_state=_state("Gamma beta."),
                plain_text="Gamma beta.",
            ),
        )
