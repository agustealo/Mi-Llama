from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import aiosqlite

from mi_llama.domain import Conversation, Role, StoredMessage


SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
ON messages(conversation_id, created_at);
"""


class ConversationRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def initialize(self) -> None:
        async with aiosqlite.connect(self._database_path) as connection:
            await connection.executescript(SCHEMA)
            await connection.commit()

    async def create_conversation(self, *, model: str, title: str | None) -> Conversation:
        now = datetime.now(UTC)
        conversation = Conversation(
            id=uuid4(),
            title=(title or "New conversation").strip() or "New conversation",
            model=model,
            created_at=now,
            updated_at=now,
        )
        async with aiosqlite.connect(self._database_path) as connection:
            await connection.execute(
                """
                INSERT INTO conversations (id, title, model, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(conversation.id),
                    conversation.title,
                    conversation.model,
                    conversation.created_at.isoformat(),
                    conversation.updated_at.isoformat(),
                ),
            )
            await connection.commit()
        return conversation

    async def list_conversations(self) -> list[Conversation]:
        async with aiosqlite.connect(self._database_path) as connection:
            connection.row_factory = aiosqlite.Row
            cursor = await connection.execute(
                """
                SELECT id, title, model, created_at, updated_at
                FROM conversations
                ORDER BY updated_at DESC
                """
            )
            rows = await cursor.fetchall()
        return [self._conversation_from_row(row) for row in rows]

    async def get_conversation(self, conversation_id: UUID) -> Conversation | None:
        async with aiosqlite.connect(self._database_path) as connection:
            connection.row_factory = aiosqlite.Row
            cursor = await connection.execute(
                """
                SELECT id, title, model, created_at, updated_at
                FROM conversations
                WHERE id = ?
                """,
                (str(conversation_id),),
            )
            row = await cursor.fetchone()
        return None if row is None else self._conversation_from_row(row)

    async def add_message(
        self,
        *,
        conversation_id: UUID,
        role: Role,
        content: str,
    ) -> StoredMessage:
        now = datetime.now(UTC)
        message = StoredMessage(
            id=uuid4(),
            conversation_id=conversation_id,
            role=role,
            content=content,
            created_at=now,
        )
        async with aiosqlite.connect(self._database_path) as connection:
            await connection.execute("BEGIN")
            cursor = await connection.execute(
                "SELECT 1 FROM conversations WHERE id = ?",
                (str(conversation_id),),
            )
            if await cursor.fetchone() is None:
                await connection.rollback()
                raise KeyError(str(conversation_id))
            await connection.execute(
                """
                INSERT INTO messages (id, conversation_id, role, content, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(message.id),
                    str(message.conversation_id),
                    message.role.value,
                    message.content,
                    message.created_at.isoformat(),
                ),
            )
            await connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now.isoformat(), str(conversation_id)),
            )
            await connection.commit()
        return message

    async def get_messages(self, conversation_id: UUID) -> list[StoredMessage]:
        async with aiosqlite.connect(self._database_path) as connection:
            connection.row_factory = aiosqlite.Row
            cursor = await connection.execute(
                """
                SELECT id, conversation_id, role, content, created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC
                """,
                (str(conversation_id),),
            )
            rows = await cursor.fetchall()
        return [self._message_from_row(row) for row in rows]

    @staticmethod
    def _conversation_from_row(row: sqlite3.Row) -> Conversation:
        return Conversation(
            id=UUID(str(row["id"])),
            title=str(row["title"]),
            model=str(row["model"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            updated_at=datetime.fromisoformat(str(row["updated_at"])),
        )

    @staticmethod
    def _message_from_row(row: sqlite3.Row) -> StoredMessage:
        return StoredMessage(
            id=UUID(str(row["id"])),
            conversation_id=UUID(str(row["conversation_id"])),
            role=Role(str(row["role"])),
            content=str(row["content"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
        )
