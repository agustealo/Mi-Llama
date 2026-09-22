from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any, Protocol, runtime_checkable

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


@runtime_checkable
class StructuredModelProvider(Protocol):
    """Optional provider capability for schema-constrained JSON output."""

    async def chat_json(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage],
        schema: dict[str, Any],
    ) -> dict[str, Any]: ...
