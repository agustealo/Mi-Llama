from __future__ import annotations

import json

import httpx
import pytest

from mi_llama.storage import SOURCE_BUCKET, SupabaseStorage


@pytest.mark.asyncio
async def test_supabase_storage_preserves_user_jwt_for_upload_and_delete() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    storage = SupabaseStorage(
        supabase_url="https://example.supabase.co",
        publishable_key="publishable",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )
    path = "11111111-1111-4111-8111-111111111111/source/version/research notes.txt"

    await storage.upload(
        access_token="user-jwt",
        bucket=SOURCE_BUCKET,
        path=path,
        media_type="text/plain",
        content=b"evidence",
    )
    await storage.delete(access_token="user-jwt", bucket=SOURCE_BUCKET, path=path)
    await storage.close()

    assert len(requests) == 2
    assert requests[0].headers["authorization"] == "Bearer user-jwt"
    assert requests[0].headers["apikey"] == "publishable"
    assert requests[0].headers["x-upsert"] == "false"
    assert "%20" in str(requests[0].url)
    assert requests[1].headers["authorization"] == "Bearer user-jwt"
    assert json.loads(requests[1].content) == {"prefixes": [path]}
