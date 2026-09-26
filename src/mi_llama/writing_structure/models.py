from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class OutlineNodeKind(StrEnum):
    PART = "part"
    CHAPTER = "chapter"
    SECTION = "section"


class OutlineNodeStatus(StrEnum):
    PLANNED = "planned"
    DRAFTING = "drafting"
    COMPLETE = "complete"
    ARCHIVED = "archived"


class ManuscriptStatus(StrEnum):
    DRAFTING = "drafting"
    REVIEW = "review"
    COMPLETE = "complete"
    ARCHIVED = "archived"


class WritingResearchLinkKind(StrEnum):
    CLAIM = "claim"
    EVIDENCE = "evidence"
    CITATION = "citation"


class OutlineNode(BaseModel):
    id: UUID
    project_id: UUID
    parent_id: UUID | None = None
    created_by: UUID
    kind: OutlineNodeKind
    title: str
    summary: str | None = None
    status: OutlineNodeStatus
    position: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime


class CreateOutlineNodeRequest(BaseModel):
    parent_id: UUID | None = None
    kind: OutlineNodeKind
    title: str = Field(min_length=1, max_length=300)
    summary: str | None = Field(default=None, max_length=8000)
    position: int = Field(default=0, ge=0)


class UpdateOutlineNodeRequest(BaseModel):
    parent_id: UUID | None = None
    kind: OutlineNodeKind | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)
    summary: str | None = Field(default=None, max_length=8000)
    status: OutlineNodeStatus | None = None
    position: int | None = Field(default=None, ge=0)


class ManuscriptDocument(BaseModel):
    id: UUID
    project_id: UUID
    outline_node_id: UUID | None = None
    created_by: UUID
    title: str
    status: ManuscriptStatus
    current_revision_id: UUID | None = None
    current_word_count: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime


class CreateManuscriptDocumentRequest(BaseModel):
    outline_node_id: UUID | None = None
    title: str = Field(min_length=1, max_length=300)


class UpdateManuscriptDocumentRequest(BaseModel):
    outline_node_id: UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)
    status: ManuscriptStatus | None = None


class ManuscriptRevision(BaseModel):
    id: UUID
    document_id: UUID
    project_id: UUID
    revision_number: int = Field(ge=1)
    created_by: UUID
    content: str
    editor_state: dict[str, Any]
    word_count: int = Field(ge=0)
    created_at: datetime


class CreateManuscriptRevisionRequest(BaseModel):
    content: str = Field(max_length=2_000_000)


class ManuscriptRevisionResult(BaseModel):
    document: ManuscriptDocument
    revision: ManuscriptRevision


class WritingResearchLink(BaseModel):
    id: UUID
    project_id: UUID
    document_id: UUID
    outline_node_id: UUID | None = None
    revision_id: UUID | None = None
    created_by: UUID
    kind: WritingResearchLinkKind
    entity_id: UUID
    character_start: int | None = Field(default=None, ge=0)
    character_end: int | None = Field(default=None, ge=1)
    created_at: datetime


class CreateWritingResearchLinkRequest(BaseModel):
    outline_node_id: UUID | None = None
    revision_id: UUID | None = None
    kind: WritingResearchLinkKind
    entity_id: UUID
    character_start: int | None = Field(default=None, ge=0)
    character_end: int | None = Field(default=None, ge=1)


class WritingWorkspaceSummary(BaseModel):
    project_id: UUID
    outline_nodes: int
    manuscript_documents: int
    current_word_count: int
    research_links: int


class WritingStructureNotFound(KeyError):
    """A project-scoped writing entity was not visible to the caller."""


class WritingValidationError(ValueError):
    """A writing operation violated a user-facing structural constraint."""
