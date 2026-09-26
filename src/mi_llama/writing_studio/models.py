from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from mi_llama.editor_state import EditorStateError, validate_editor_state
from mi_llama.writing_structure.models import ManuscriptDocument, ManuscriptRevision


class WritingProposalOperation(StrEnum):
    REWRITE = "rewrite"
    IMPROVE = "improve"
    EXPAND = "expand"
    CONDENSE = "condense"
    CONTINUE = "continue"
    CUSTOM = "custom"


class WritingProposalStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    STALE = "stale"


class ManuscriptDraft(BaseModel):
    id: UUID
    project_id: UUID
    document_id: UUID
    created_by: UUID
    updated_by: UUID
    base_revision_id: UUID | None = None
    version: int = Field(ge=1)
    editor_state: dict[str, Any]
    plain_text: str = Field(max_length=2_000_000)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_editor_projection(self) -> Self:
        try:
            validate_editor_state(self.editor_state, self.plain_text)
        except EditorStateError as exc:
            raise ValueError(str(exc)) from exc
        return self


class SaveManuscriptDraftRequest(BaseModel):
    expected_version: int | None = Field(default=None, ge=1)
    base_revision_id: UUID | None = None
    editor_state: dict[str, Any]
    plain_text: str = Field(max_length=2_000_000)

    @model_validator(mode="after")
    def validate_editor_projection(self) -> Self:
        try:
            validate_editor_state(self.editor_state, self.plain_text)
        except EditorStateError as exc:
            raise ValueError(str(exc)) from exc
        return self


class CheckpointManuscriptDraftRequest(BaseModel):
    expected_draft_version: int = Field(ge=1)


class CheckpointManuscriptDraftResult(BaseModel):
    document: ManuscriptDocument
    revision: ManuscriptRevision
    draft: ManuscriptDraft


class CreateDocumentConversationRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    title: str | None = Field(default=None, max_length=120)


class ManuscriptConversationContextRequest(BaseModel):
    draft_version: int = Field(ge=1)
    character_start: int | None = Field(default=None, ge=0)
    character_end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if (self.character_start is None) != (self.character_end is None):
            raise ValueError("character_start and character_end must be provided together")
        if (
            self.character_start is not None
            and self.character_end is not None
            and self.character_end <= self.character_start
        ):
            raise ValueError("character_end must be greater than character_start")
        return self


class SendDocumentConversationMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=32_000)
    context: ManuscriptConversationContextRequest


class WritingProposal(BaseModel):
    id: UUID
    project_id: UUID
    document_id: UUID
    created_by: UUID
    base_draft_version: int = Field(ge=1)
    base_revision_id: UUID | None = None
    operation: WritingProposalOperation
    model: str
    prompt: str | None = None
    selection_start: int = Field(ge=0)
    selection_end: int = Field(ge=1)
    selection_hash: str = Field(min_length=64, max_length=64)
    original_text: str = Field(min_length=1, max_length=200_000)
    proposed_text: str = Field(min_length=1, max_length=200_000)
    context_manifest: dict[str, Any]
    status: WritingProposalStatus
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CreateWritingProposalRequest(BaseModel):
    expected_draft_version: int = Field(ge=1)
    operation: WritingProposalOperation
    model: str = Field(min_length=1, max_length=200)
    selection_start: int = Field(ge=0)
    selection_end: int = Field(ge=1)
    prompt: str | None = Field(default=None, max_length=4000)


class ApplyWritingProposalRequest(BaseModel):
    expected_draft_version: int = Field(ge=1)


class WritingProposalApplicationResult(BaseModel):
    draft: ManuscriptDraft
    proposal: WritingProposal
