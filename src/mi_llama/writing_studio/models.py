from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

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


class SaveManuscriptDraftRequest(BaseModel):
    expected_version: int | None = Field(default=None, ge=1)
    base_revision_id: UUID | None = None
    editor_state: dict[str, Any]
    plain_text: str = Field(max_length=2_000_000)


class CheckpointManuscriptDraftRequest(BaseModel):
    expected_draft_version: int = Field(ge=1)


class CheckpointManuscriptDraftResult(BaseModel):
    document: ManuscriptDocument
    revision: ManuscriptRevision
    draft: ManuscriptDraft


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
