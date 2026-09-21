from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ProviderStatus(StrEnum):
    READY = "ready"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"


class ChatMessage(BaseModel):
    role: Role
    content: str = Field(min_length=1)


class StoredMessage(ChatMessage):
    id: UUID
    conversation_id: UUID
    created_at: datetime


class Conversation(BaseModel):
    id: UUID
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
