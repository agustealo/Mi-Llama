from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from pathlib import Path

from fastapi.testclient import TestClient

from mi_llama.config import Settings
from mi_llama.domain import ChatMessage, ModelInfo, ProviderHealth, ProviderStatus
from mi_llama.main import create_app


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


def test_streaming_chat_persists_both_sides_of_conversation(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings=settings, provider=FakeProvider())

    with TestClient(app) as client:
        models = client.get("/api/models")
        assert models.status_code == 200
        assert models.json()[0]["name"] == "llama3.2:latest"

        created = client.post(
            "/api/conversations",
            json={"model": "llama3.2:latest", "title": "First real chat"},
        )
        assert created.status_code == 201
        conversation_id = created.json()["id"]

        streamed = client.post(
            f"/api/conversations/{conversation_id}/messages",
            json={"content": "Hello"},
        )
        assert streamed.status_code == 200
        assert '"type": "token"' in streamed.text
        assert '"content": "Hello"' in streamed.text
        assert '"type": "done"' in streamed.text

        restored = client.get(f"/api/conversations/{conversation_id}")
        assert restored.status_code == 200
        messages = restored.json()["messages"]
        assert [(item["role"], item["content"]) for item in messages] == [
            ("user", "Hello"),
            ("assistant", "Hello from Mi-Llama"),
        ]
