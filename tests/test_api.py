from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from mi_llama.config import Settings
from mi_llama.domain import (
    ChatMessage,
    Conversation,
    LearningEvent,
    LearningSignal,
    ModelInfo,
    Project,
    ProviderHealth,
    ProviderStatus,
    Role,
    StoredMessage,
)
from mi_llama.main import create_app

USER_ID = UUID("11111111-1111-1111-1111-111111111111")
PROJECT_ID = UUID("22222222-2222-2222-2222-222222222222")
CONVERSATION_ID = UUID("33333333-3333-3333-3333-333333333333")


class FakeProvider:
    async def health(self) -> ProviderHealth:
        return ProviderHealth(status=ProviderStatus.READY)

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(name="llama3.2:latest")]

    async def chat(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage],
    ) -> str:
        return "Hello from Mi-Llama"

    async def chat_stream(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage],
    ) -> AsyncIterator[str]:
        assert model == "llama3.2:latest"
        assert messages[-1].content == "Hello"
        yield "Hello"
        yield " from Mi-Llama"

    async def close(self) -> None:
        return None


class MemoryRepository:
    def __init__(self) -> None:
        self.project: Project | None = None
        self.conversation: Conversation | None = None
        self.messages: list[StoredMessage] = []
        self.seen_tokens: list[str] = []

    def _record(self, access_token: str) -> None:
        self.seen_tokens.append(access_token)

    async def close(self) -> None:
        return None

    async def create_project(
        self, *, access_token: str, title: str, description: str | None
    ) -> Project:
        self._record(access_token)
        now = datetime.now(UTC)
        self.project = Project(
            id=PROJECT_ID,
            owner_id=USER_ID,
            title=title,
            description=description,
            created_at=now,
            updated_at=now,
        )
        return self.project

    async def list_projects(self, *, access_token: str) -> list[Project]:
        self._record(access_token)
        return [] if self.project is None else [self.project]

    async def get_project(self, *, access_token: str, project_id: UUID) -> Project | None:
        self._record(access_token)
        if self.project is None or self.project.id != project_id:
            return None
        return self.project

    async def create_conversation(
        self,
        *,
        access_token: str,
        project_id: UUID,
        model: str,
        title: str | None,
    ) -> Conversation:
        self._record(access_token)
        now = datetime.now(UTC)
        self.conversation = Conversation(
            id=CONVERSATION_ID,
            project_id=project_id,
            created_by=USER_ID,
            title=title or "New conversation",
            model=model,
            created_at=now,
            updated_at=now,
        )
        return self.conversation

    async def list_conversations(
        self, *, access_token: str, project_id: UUID
    ) -> list[Conversation]:
        self._record(access_token)
        if self.conversation is None or self.conversation.project_id != project_id:
            return []
        return [self.conversation]

    async def get_conversation(
        self, *, access_token: str, conversation_id: UUID
    ) -> Conversation | None:
        self._record(access_token)
        if self.conversation is None or self.conversation.id != conversation_id:
            return None
        return self.conversation

    async def add_message(
        self,
        *,
        access_token: str,
        conversation_id: UUID,
        role: Role,
        content: str,
    ) -> StoredMessage:
        self._record(access_token)
        message = StoredMessage(
            id=uuid4(),
            conversation_id=conversation_id,
            created_by=USER_ID,
            role=role,
            content=content,
            created_at=datetime.now(UTC),
        )
        self.messages.append(message)
        return message

    async def get_messages(
        self, *, access_token: str, conversation_id: UUID
    ) -> list[StoredMessage]:
        self._record(access_token)
        return [message for message in self.messages if message.conversation_id == conversation_id]

    async def add_learning_signal(
        self,
        *,
        access_token: str,
        project_id: UUID,
        event_type: LearningEvent,
        entity_type: str | None,
        entity_id: UUID | None,
        metadata: dict[str, Any],
    ) -> LearningSignal:
        self._record(access_token)
        return LearningSignal(
            id=uuid4(),
            project_id=project_id,
            user_id=USER_ID,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata=metadata,
            created_at=datetime.now(UTC),
        )


def test_project_api_requires_supabase_identity() -> None:
    app = create_app(settings=Settings(_env_file=None), provider=FakeProvider(), repository=MemoryRepository())

    with TestClient(app) as client:
        response = client.get("/api/projects")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_project_chat_and_learning_signal_keep_user_scope() -> None:
    repository = MemoryRepository()
    app = create_app(settings=Settings(_env_file=None), provider=FakeProvider(), repository=repository)
    headers = {"Authorization": "Bearer test-user-jwt"}

    with TestClient(app) as client:
        created_project = client.post(
            "/api/projects",
            headers=headers,
            json={"title": "Book research", "description": "Primary research project"},
        )
        assert created_project.status_code == 201
        assert created_project.json()["id"] == str(PROJECT_ID)

        created_conversation = client.post(
            f"/api/projects/{PROJECT_ID}/conversations",
            headers=headers,
            json={"model": "llama3.2:latest", "title": "Evidence review"},
        )
        assert created_conversation.status_code == 201
        assert created_conversation.json()["project_id"] == str(PROJECT_ID)

        streamed = client.post(
            f"/api/conversations/{CONVERSATION_ID}/messages",
            headers=headers,
            json={"content": "Hello"},
        )
        assert streamed.status_code == 200
        assert '"type": "token"' in streamed.text
        assert '"type": "done"' in streamed.text

        restored = client.get(f"/api/conversations/{CONVERSATION_ID}", headers=headers)
        assert restored.status_code == 200
        assert [(item["role"], item["content"]) for item in restored.json()["messages"]] == [
            ("user", "Hello"),
            ("assistant", "Hello from Mi-Llama"),
        ]

        signal = client.post(
            f"/api/projects/{PROJECT_ID}/learning-signals",
            headers=headers,
            json={
                "event_type": "research_result_saved",
                "entity_type": "source",
                "entity_id": "44444444-4444-4444-4444-444444444444",
                "metadata": {"rank": 2},
            },
        )
        assert signal.status_code == 201
        assert signal.json()["event_type"] == "research_result_saved"

    assert repository.seen_tokens
    assert set(repository.seen_tokens) == {"test-user-jwt"}
