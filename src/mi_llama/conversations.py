from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from time import monotonic
from typing import Protocol, runtime_checkable
from uuid import UUID

from mi_llama.domain import ChatMessage, ConversationWithMessages, Role
from mi_llama.providers.base import ModelProvider
from mi_llama.repositories import Repository, RepositoryError

_REPLY_LEASE_SECONDS = 600
_REPLY_LEASE_RENEW_INTERVAL_SECONDS = 120


@runtime_checkable
class ConversationLeaseRepository(Protocol):
    async def acquire_conversation_reply_lease(
        self,
        *,
        access_token: str,
        conversation_id: UUID,
        ttl_seconds: int,
    ) -> UUID: ...

    async def renew_conversation_reply_lease(
        self,
        *,
        access_token: str,
        conversation_id: UUID,
        lease_token: UUID,
        ttl_seconds: int,
    ) -> None: ...

    async def release_conversation_reply_lease(
        self,
        *,
        access_token: str,
        conversation_id: UUID,
        lease_token: UUID,
    ) -> None: ...


class ConversationService:
    def __init__(
        self,
        *,
        repository: Repository,
        provider: ModelProvider,
    ) -> None:
        self._repository = repository
        self._provider = provider
        self._turn_locks: dict[UUID, asyncio.Lock] = {}

    async def get_conversation(
        self,
        *,
        access_token: str,
        conversation_id: UUID,
    ) -> ConversationWithMessages | None:
        conversation = await self._repository.get_conversation(
            access_token=access_token,
            conversation_id=conversation_id,
        )
        if conversation is None:
            return None
        messages = await self._repository.get_messages(
            access_token=access_token,
            conversation_id=conversation_id,
        )
        return ConversationWithMessages(conversation=conversation, messages=messages)

    async def stream_reply(
        self,
        *,
        access_token: str,
        conversation_id: UUID,
        user_content: str,
    ) -> AsyncIterator[str]:
        lock = self._turn_locks.setdefault(conversation_id, asyncio.Lock())
        async with lock:
            lease_repository = (
                self._repository
                if isinstance(self._repository, ConversationLeaseRepository)
                else None
            )
            lease_token: UUID | None = None
            lease_last_renewed: float | None = None
            if lease_repository is not None:
                lease_token = await lease_repository.acquire_conversation_reply_lease(
                    access_token=access_token,
                    conversation_id=conversation_id,
                    ttl_seconds=_REPLY_LEASE_SECONDS,
                )
                lease_last_renewed = monotonic()

            try:
                conversation = await self._repository.get_conversation(
                    access_token=access_token,
                    conversation_id=conversation_id,
                )
                if conversation is None:
                    raise KeyError(str(conversation_id))

                await self._repository.add_message(
                    access_token=access_token,
                    conversation_id=conversation_id,
                    role=Role.USER,
                    content=user_content,
                )

                stored_messages = await self._repository.get_messages(
                    access_token=access_token,
                    conversation_id=conversation_id,
                )
                provider_messages = [
                    ChatMessage(role=message.role, content=message.content)
                    for message in stored_messages
                ]

                reply_parts: list[str] = []
                async for chunk in self._provider.chat_stream(
                    model=conversation.model,
                    messages=provider_messages,
                ):
                    if (
                        lease_repository is not None
                        and lease_token is not None
                        and lease_last_renewed is not None
                        and monotonic() - lease_last_renewed
                        >= _REPLY_LEASE_RENEW_INTERVAL_SECONDS
                    ):
                        await lease_repository.renew_conversation_reply_lease(
                            access_token=access_token,
                            conversation_id=conversation_id,
                            lease_token=lease_token,
                            ttl_seconds=_REPLY_LEASE_SECONDS,
                        )
                        lease_last_renewed = monotonic()
                    reply_parts.append(chunk)
                    yield chunk

                reply = "".join(reply_parts).strip()
                if reply:
                    await self._repository.add_message(
                        access_token=access_token,
                        conversation_id=conversation_id,
                        role=Role.ASSISTANT,
                        content=reply,
                    )
            finally:
                if lease_repository is not None and lease_token is not None:
                    # The durable lease has an expiry and cannot outlive its TTL. A failed cleanup
                    # must not turn an otherwise completed model reply into an API failure.
                    with suppress(RepositoryError):
                        await lease_repository.release_conversation_reply_lease(
                            access_token=access_token,
                            conversation_id=conversation_id,
                            lease_token=lease_token,
                        )
