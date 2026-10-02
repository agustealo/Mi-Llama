from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest

from mi_llama.repositories import RepositoryAuthenticationError, SupabaseRepository

PROJECT_ID = UUID("22222222-2222-2222-2222-222222222222")
USER_ID = UUID("11111111-1111-1111-1111-111111111111")


@pytest.mark.asyncio
async def test_supabase_repository_applies_database_defaults_to_first_project_insert() -> None:
    now = datetime.now(UTC).isoformat()

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/rest/v1/projects"
        assert request.headers["authorization"] == "Bearer user-access-token"
        assert request.headers["apikey"] == "publishable-key"
        assert request.headers["prefer"] == "return=representation,missing=default"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload == {"title": "Research project", "description": "Evidence library"}
        assert "owner_id" not in payload
        return httpx.Response(
            201,
            json=[
                {
                    "id": str(PROJECT_ID),
                    "owner_id": str(USER_ID),
                    "title": "Research project",
                    "description": "Evidence library",
                    "created_at": now,
                    "updated_at": now,
                }
            ],
        )

    repository = SupabaseRepository(
        supabase_url="https://example.supabase.co",
        publishable_key="publishable-key",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )
    try:
        project = await repository.create_project(
            access_token="user-access-token",
            title="Research project",
            description="Evidence library",
        )
    finally:
        await repository.close()

    assert project.id == PROJECT_ID
    assert project.owner_id == USER_ID


@pytest.mark.asyncio
async def test_supabase_repository_does_not_hide_authentication_failure() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "invalid JWT"})

    repository = SupabaseRepository(
        supabase_url="https://example.supabase.co",
        publishable_key="publishable-key",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(RepositoryAuthenticationError):
            await repository.list_projects(access_token="expired-token")
    finally:
        await repository.close()


@pytest.mark.asyncio
async def test_supabase_repository_does_not_apply_missing_default_to_rpc_calls() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/rest/v1/rpc/example"
        assert "prefer" not in request.headers
        return httpx.Response(200, json=[])

    repository = SupabaseRepository(
        supabase_url="https://example.supabase.co",
        publishable_key="publishable-key",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )
    try:
        rows = await repository._request_rows(
            "POST",
            "/rpc/example",
            access_token="user-access-token",
            json={"value": "test"},
        )
    finally:
        await repository.close()

    assert rows == []
