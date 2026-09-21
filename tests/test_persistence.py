from __future__ import annotations

from pathlib import Path

import pytest

from mi_llama.domain import Role
from mi_llama.persistence import ConversationRepository


@pytest.mark.asyncio
async def test_conversation_and_messages_survive_repository_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "mi-llama.sqlite3"

    first = ConversationRepository(database_path)
    await first.initialize()
    conversation = await first.create_conversation(
        model="llama3.2:latest",
        title="Persistent chat",
    )
    await first.add_message(
        conversation_id=conversation.id,
        role=Role.USER,
        content="Remember this after restart.",
    )

    second = ConversationRepository(database_path)
    await second.initialize()
    restored = await second.get_conversation(conversation.id)
    messages = await second.get_messages(conversation.id)

    assert restored is not None
    assert restored.title == "Persistent chat"
    assert restored.model == "llama3.2:latest"
    assert [(message.role, message.content) for message in messages] == [
        (Role.USER, "Remember this after restart.")
    ]
