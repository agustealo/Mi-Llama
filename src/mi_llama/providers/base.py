from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Protocol

from mi_llama.domain import ChatMessage, ModelInfo, ProviderHealth


class ModelProvider(Protocol):
    """Provider contract used by application services."""

    async def health(self) -> ProviderHealth: ...

    async def list_models(self) -> list[ModelInfo]: ...

    async def chat(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage],
    ) -> str: ...

    def chat_stream(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage],
    ) -> AsyncIterator[str]: ...

    async def close(self) -> None: ...
