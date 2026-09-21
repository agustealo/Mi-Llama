from __future__ import annotations

import httpx
import pytest

from mi_llama.domain import ChatMessage, Role
from mi_llama.providers.ollama import OllamaProvider


def _transport(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/api/tags":
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "llama3.2:latest",
                        "modified_at": "2026-09-21T12:00:00Z",
                        "size": 2_000_000_000,
                        "digest": "abc123",
                    }
                ]
            },
        )
    if request.url.path == "/api/chat":
        return httpx.Response(
            200,
            content=(
                b'{"message":{"role":"assistant","content":"Hello"},"done":false}\n'
                b'{"message":{"role":"assistant","content":" world"},"done":false}\n'
                b'{"message":{"role":"assistant","content":""},"done":true}\n'
            ),
            headers={"content-type": "application/x-ndjson"},
        )
    return httpx.Response(404)


@pytest.mark.asyncio
async def test_lists_real_ollama_models() -> None:
    provider = OllamaProvider(
        base_url="http://ollama.test",
        request_timeout_seconds=5,
        connect_timeout_seconds=1,
        transport=httpx.MockTransport(_transport),
    )
    try:
        models = await provider.list_models()
    finally:
        await provider.close()

    assert [model.name for model in models] == ["llama3.2:latest"]
    assert models[0].digest == "abc123"


@pytest.mark.asyncio
async def test_streams_native_ollama_chat_tokens() -> None:
    provider = OllamaProvider(
        base_url="http://ollama.test",
        request_timeout_seconds=5,
        connect_timeout_seconds=1,
        transport=httpx.MockTransport(_transport),
    )
    chunks: list[str] = []
    try:
        async for chunk in provider.chat_stream(
            model="llama3.2:latest",
            messages=[ChatMessage(role=Role.USER, content="Hi")],
        ):
            chunks.append(chunk)
    finally:
        await provider.close()

    assert chunks == ["Hello", " world"]
