from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ProjectRole(StrEnum):
    OWNER = "owner"
    EDITOR = "editor"
    RESEARCHER = "researcher"
    REVIEWER = "reviewer"
    READER = "reader"


class LearningEvent(StrEnum):
    RESEARCH_RESULT_IMPRESSION = "research_result_impression"
    RESEARCH_RESULT_OPENED = "research_result_opened"
    RESEARCH_RESULT_SAVED = "research_result_saved"
    RESEARCH_RESULT_REJECTED = "research_result_rejected"
    SOURCE_CITED = "source_cited"
    SOURCE_UNTRUSTED = "source_untrusted"
    CITATION_ACCEPTED = "citation_accepted"
    CITATION_REJECTED = "citation_rejected"
    AI_EDIT_ACCEPTED = "ai_edit_accepted"
    AI_EDIT_REJECTED = "ai_edit_rejected"
    RESEARCH_SUGGESTION_ACCEPTED = "research_suggestion_accepted"
    RESEARCH_SUGGESTION_REJECTED = "research_suggestion_rejected"
    WRITING_FINDING_CONFIRMED = "writing_finding_confirmed"
    WRITING_FINDING_DISMISSED = "writing_finding_dismissed"
    WRITING_GAP_CREATED = "writing_gap_created"


class ProviderStatus(StrEnum):
    READY = "ready"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"


class SourceKind(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    EPUB = "epub"
    TEXT = "text"
    MARKDOWN = "markdown"
    HTML = "html"


class SourceStatus(StrEnum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class ResearchIndexStatus(StrEnum):
    NOT_INDEXED = "not_indexed"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"
    DISABLED = "disabled"


class Project(BaseModel):
    id: UUID
    owner_id: UUID
    title: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class CreateProjectRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)


class ChatMessage(BaseModel):
    role: Role
    content: str = Field(min_length=1)


class StoredMessage(ChatMessage):
    id: UUID
    conversation_id: UUID
    created_by: UUID
    created_at: datetime


class Conversation(BaseModel):
    id: UUID
    project_id: UUID
    created_by: UUID
    title: str
    model: str
    created_at: datetime
    updated_at: datetime


class ModelInfo(BaseModel):
    name: str
    modified_at: datetime | None = None
    size: int | None = None
    digest: str | None = None


class ProviderHealth(BaseModel):
    provider: Literal["ollama"] = "ollama"
    status: ProviderStatus
    detail: str | None = None


class CreateConversationRequest(BaseModel):
    model: str = Field(min_length=1)
    title: str | None = Field(default=None, max_length=120)


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1)


class ConversationWithMessages(BaseModel):
    conversation: Conversation
    messages: list[StoredMessage]


class LearningSignal(BaseModel):
    id: UUID
    project_id: UUID
    user_id: UUID
    event_type: LearningEvent
    entity_type: str | None = None
    entity_id: UUID | None = None
    metadata: dict[str, Any]
    created_at: datetime


class CreateLearningSignalRequest(BaseModel):
    event_type: LearningEvent
    entity_type: str | None = Field(default=None, max_length=80)
    entity_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Source(BaseModel):
    id: UUID
    project_id: UUID
    created_by: UUID
    filename: str
    media_type: str
    kind: SourceKind
    checksum_sha256: str
    size_bytes: int
    status: SourceStatus
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class SourceVersion(BaseModel):
    id: UUID
    source_id: UUID
    project_id: UUID
    created_by: UUID
    version_number: int
    storage_path: str
    checksum_sha256: str
    parser: str
    character_count: int
    status: SourceStatus
    error_message: str | None = None
    research_status: ResearchIndexStatus
    research_error: str | None = None
    created_at: datetime


class SourceChunk(BaseModel):
    id: UUID
    source_version_id: UUID
    source_id: UUID
    project_id: UUID
    ordinal: int
    location: str | None = None
    content: str
    character_start: int
    character_end: int
    created_at: datetime | None = None


class SourceIngestResult(BaseModel):
    source: Source
    version: SourceVersion
    chunk_count: int
    deduplicated: bool


class ResearchQueryRequest(BaseModel):
    query: str = Field(min_length=2, max_length=4000)
    limit: int = Field(default=8, ge=1, le=25)


class ResearchHit(BaseModel):
    source_id: UUID
    source_version_id: UUID
    chunk_id: UUID
    source_filename: str
    location: str | None = None
    ordinal: int
    content: str
    relevance: float = Field(ge=0)


class ResearchResponse(BaseModel):
    project_id: UUID
    query: str
    hits: list[ResearchHit]
