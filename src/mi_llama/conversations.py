from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from mi_llama.domain import ChatMessage, ConversationWithMessages, Role
from mi_llama.persistence import ConversationRepository
from mi_llama.providers.base import ModelProvider


class ConversationService:
    def __init__(
        self,
        *,
        repository: ConversationRepository,
        provider: ModelProvider,
    ) -> None:
        self._repository = repository
        self._provider = provider

    async def get_conversation(self, conversation_id: UUID) -> ConversationWithMessages | None:
        conversation = await self._repository.get_conversation(conversation_id)
        if conversation is None:
            return None
        messages = await self._repository.get_messages(conversation_id)
        return ConversationWithMessages(conversation=conversation, messages=messages)

    async def stream_reply(
        self,
        *,
        conversation_id: UUID,
        user_content: str,
    ) -> AsyncIterator[str]:
        conversation = await self._repository.get_conversation(conversation_id)
        if conversation is None:
            raise KeyError(str(conversation_id))

        await self._repository.add_message(
            conversation_id=conversation_id,
            role=Role.USER,
            content=user_content,
        )

        stored_messages = await self._repository.get_messages(conversation_id)
        provider_messages = [
            ChatMessage(role=message.role, content=message.content) for message in stored_messages
        ]

        reply_parts: list[str] = []
        async for chunk in self._provider.chat_stream(
            model=conversation.model,
            messages=provider_messages,
        ):
            reply_parts.append(chunk)
            yield chunk

        reply = "".join(reply_parts).strip()
        if reply:
            await self._repository.add_message(
                conversation_id=conversation_id,
                role=Role.ASSISTANT,
                content=reply,
            )
