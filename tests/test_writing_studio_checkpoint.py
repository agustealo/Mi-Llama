from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from mi_llama.repositories import RepositoryError
from mi_llama.writing_structure import ManuscriptDocument, ManuscriptRevision, ManuscriptStatus
from mi_llama.writing_studio import (
    CheckpointManuscriptDraftRequest,
    DraftVersionConflict,
    ManuscriptDraft,
    WritingStudioService,
)

PROJECT_ID = UUID("11111111-1111-1111-1111-111111111111")
DOCUMENT_ID = UUID("22222222-2222-2222-2222-222222222222")
USER_ID = UUID("33333333-3333-3333-3333-333333333333")


def _now() -> datetime:
    return datetime.now(UTC)


class UnusedProvider:
    async def chat_json(self, **kwargs: Any) -> dict[str, Any]:
        del kwargs
        raise AssertionError("checkpointing must not invoke the model")


class CheckpointRepository:
    def __init__(self, *, stale: bool = False) -> None:
        now = _now()
        self.stale = stale
        self.document = ManuscriptDocument(
            id=DOCUMENT_ID,
            project_id=PROJECT_ID,
            outline_node_id=None,
            created_by=USER_ID,
            title="Draft",
            status=ManuscriptStatus.DRAFTING,
            current_revision_id=None,
            current_word_count=0,
            created_at=now,
            updated_at=now,
        )
        self.draft = ManuscriptDraft(
            id=uuid4(),
            project_id=PROJECT_ID,
            document_id=DOCUMENT_ID,
            created_by=USER_ID,
            updated_by=USER_ID,
            base_revision_id=None,
            version=4,
            editor_state={"schema": "plain_text_v1", "text": "One two three"},
            plain_text="One two three",
            created_at=now,
            updated_at=now,
        )

    async def get_manuscript_document(
        self, *, access_token: str, project_id: UUID, document_id: UUID
    ) -> ManuscriptDocument | None:
        del access_token
        if project_id == PROJECT_ID and document_id == DOCUMENT_ID:
            return self.document
        return None

    async def get_manuscript_draft(
        self, *, access_token: str, project_id: UUID, document_id: UUID
    ) -> ManuscriptDraft | None:
        del access_token
        if project_id == PROJECT_ID and document_id == DOCUMENT_ID:
            return self.draft
        return None

    async def checkpoint_manuscript_draft(
        self,
        *,
        access_token: str,
        project_id: UUID,
        document_id: UUID,
        expected_draft_version: int,
    ) -> ManuscriptRevision:
        del access_token, project_id, document_id
        if self.stale or expected_draft_version != self.draft.version:
            raise RepositoryError("manuscript draft version is stale")
        revision = ManuscriptRevision(
            id=uuid4(),
            document_id=DOCUMENT_ID,
            project_id=PROJECT_ID,
            revision_number=1,
            created_by=USER_ID,
            content=self.draft.plain_text,
            word_count=3,
            created_at=_now(),
        )
        self.document = self.document.model_copy(
            update={
                "current_revision_id": revision.id,
                "current_word_count": revision.word_count,
                "updated_at": _now(),
            }
        )
        self.draft = self.draft.model_copy(
            update={
                "base_revision_id": revision.id,
                "version": self.draft.version + 1,
                "updated_at": _now(),
            }
        )
        return revision


@pytest.mark.asyncio
async def test_checkpoint_returns_one_coherent_document_revision_and_draft_state() -> None:
    repository = CheckpointRepository()
    service = WritingStudioService(
        repository=repository,  # type: ignore[arg-type]
        provider=UnusedProvider(),  # type: ignore[arg-type]
    )

    result = await service.checkpoint_draft(
        access_token="jwt",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        request=CheckpointManuscriptDraftRequest(expected_draft_version=4),
    )

    assert result.revision.content == "One two three"
    assert result.document.current_revision_id == result.revision.id
    assert result.draft.base_revision_id == result.revision.id
    assert result.draft.version == 5


@pytest.mark.asyncio
async def test_checkpoint_maps_database_version_race_to_draft_conflict() -> None:
    repository = CheckpointRepository(stale=True)
    service = WritingStudioService(
        repository=repository,  # type: ignore[arg-type]
        provider=UnusedProvider(),  # type: ignore[arg-type]
    )

    with pytest.raises(DraftVersionConflict, match="stale"):
        await service.checkpoint_draft(
            access_token="jwt",
            project_id=PROJECT_ID,
            document_id=DOCUMENT_ID,
            request=CheckpointManuscriptDraftRequest(expected_draft_version=4),
        )
