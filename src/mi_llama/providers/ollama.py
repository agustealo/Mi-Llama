from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import Any, cast

import httpx

from mi_llama.domain import ChatMessage, ModelInfo, ProviderHealth, ProviderStatus
from mi_llama.providers.errors import ProviderProtocolError, ProviderUnavailableError


class OllamaProvider:
    """Ollama provider using the current native HTTP API."""

    def __init__(
        self,
        *,
        base_url: str,
        request_timeout_seconds: float,
        connect_timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        timeout = httpx.Timeout(
            request_timeout_seconds,
            connect=connect_timeout_seconds,
        )
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
        )

    async def health(self) -> ProviderHealth:
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            return ProviderHealth(
                status=ProviderStatus.UNAVAILABLE,
                detail=str(exc),
            )
        return ProviderHealth(status=ProviderStatus.READY)

    async def list_models(self) -> list[ModelInfo]:
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(str(exc)) from exc

        payload = cast(dict[str, Any], response.json())
        raw_models = payload.get("models")
        if not isinstance(raw_models, list):
            raise ProviderProtocolError("Ollama /api/tags response is missing a models list")

        models: list[ModelInfo] = []
        for raw_model in raw_models:
            if not isinstance(raw_model, dict):
                continue
            name = raw_model.get("name") or raw_model.get("model")
            if not isinstance(name, str) or not name:
                continue
            modified_at = raw_model.get("modified_at")
            parsed_modified_at: datetime | None = None
            if isinstance(modified_at, str):
                try:
                    parsed_modified_at = datetime.fromisoformat(modified_at.replace("Z", "+00:00"))
                except ValueError:
                    parsed_modified_at = None
            size = raw_model.get("size")
            digest = raw_model.get("digest")
            models.append(
                ModelInfo(
                    name=name,
                    modified_at=parsed_modified_at,
                    size=size if isinstance(size, int) else None,
                    digest=digest if isinstance(digest, str) else None,
                )
            )
        return models

    async def chat(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage],
    ) -> str:
        body = await self._chat_response(
            payload={
                "model": model,
                "messages": [message.model_dump(mode="json") for message in messages],
                "stream": False,
            }
        )
        message = body.get("message")
        if not isinstance(message, dict):
            raise ProviderProtocolError("Ollama chat response is missing message")
        content = message.get("content")
        if not isinstance(content, str):
            raise ProviderProtocolError("Ollama chat response is missing message.content")
        return content

    async def chat_json(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage],
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        body = await self._chat_response(
            payload={
                "model": model,
                "messages": [message.model_dump(mode="json") for message in messages],
                "stream": False,
                "format": schema,
                "options": {"temperature": 0},
            }
        )
        message = body.get("message")
        if not isinstance(message, dict):
            raise ProviderProtocolError("Ollama structured response is missing message")
        content = message.get("content")
        if not isinstance(content, str):
            raise ProviderProtocolError("Ollama structured response is missing message.content")
        try:
            parsed = cast(object, json.loads(content))
        except json.JSONDecodeError as exc:
            raise ProviderProtocolError("Ollama structured response is invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise ProviderProtocolError("Ollama structured response must be a JSON object")
        return cast(dict[str, Any], parsed)

    async def _chat_response(self, *, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.post("/api/chat", json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(str(exc)) from exc
        try:
            body = cast(object, response.json())
        except ValueError as exc:
            raise ProviderProtocolError("Ollama returned invalid JSON") from exc
        if not isinstance(body, dict):
            raise ProviderProtocolError("Ollama chat response must be a JSON object")
        return cast(dict[str, Any], body)

    async def chat_stream(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage],
    ) -> AsyncIterator[str]:
        payload = {
            "model": model,
            "messages": [message.model_dump(mode="json") for message in messages],
            "stream": True,
        }
        try:
            async with self._client.stream("POST", "/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        event = cast(dict[str, Any], json.loads(line))
                    except json.JSONDecodeError as exc:
                        raise ProviderProtocolError("Invalid JSON in Ollama stream") from exc
                    message = event.get("message")
                    if isinstance(message, dict):
                        content = message.get("content")
                        if isinstance(content, str) and content:
                            yield content
                    if event.get("done") is True:
                        break
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(str(exc)) from exc

    async def close(self) -> None:
        await self._client.aclose()
