from __future__ import annotations

import json

import httpx
import pytest

from mi_llama.domain import ChatMessage, Role
from mi_llama.providers.ollama import OllamaProvider


def _structured_transport(request: httpx.Request) -> httpx.Response:
    if request.url.path != "/api/chat":
        return httpx.Response(404)
    payload = json.loads(request.content)
    assert payload["stream"] is False
    assert payload["format"]["type"] == "object"
    assert payload["options"]["temperature"] == 0
    return httpx.Response(
        200,
        json={
            "message": {
                "role": "assistant",
                "content": '{"claims":[{"sentence_index":0}]}',
            },
            "done": True,
        },
    )


@pytest.mark.asyncio
async def test_ollama_structured_output_passes_json_schema() -> None:
    provider = OllamaProvider(
        base_url="http://ollama.test",
        request_timeout_seconds=5,
        connect_timeout_seconds=1,
        transport=httpx.MockTransport(_structured_transport),
    )
    try:
        result = await provider.chat_json(
            model="llama3.2:latest",
            messages=[ChatMessage(role=Role.USER, content="Classify this.")],
            schema={
                "type": "object",
                "properties": {
                    "claims": {
                        "type": "array",
                        "items": {"type": "object"},
                    }
                },
                "required": ["claims"],
            },
        )
    finally:
        await provider.close()

    assert result["claims"] == [{"sentence_index": 0}]
