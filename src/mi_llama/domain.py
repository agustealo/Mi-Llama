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


class ProviderStatus(StrEnum):
    READY = "ready"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"


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
