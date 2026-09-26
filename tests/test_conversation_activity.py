from pathlib import Path
from uuid import UUID

import httpx
import pytest

from mi_llama.writing_studio.repository import SupabaseWritingStudioRepository

ROOT = Path(__file__).parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "20260926154500_conversation_activity.sql"
PROJECT_ID = UUID("22222222-2222-2222-2222-222222222222")


def test_conversation_activity_view_keeps_rls_and_message_recency() -> None:
    sql = MIGRATION.read_text()

    assert "create view public.conversation_activity" in sql
    assert "security_invoker = true" in sql
    assert "left join public.messages" in sql
    assert "max(message.created_at)" in sql
    assert "greatest(" in sql
    assert "grant select on public.conversation_activity to authenticated" in sql
    assert "security definer" not in sql.lower()


@pytest.mark.asyncio
async def test_writing_studio_lists_conversations_by_activity_view() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/rest/v1/conversation_activity"
        assert request.url.params["project_id"] == f"eq.{PROJECT_ID}"
        assert request.url.params["order"] == "activity_at.desc,created_at.desc"
        return httpx.Response(
            200,
            json=[
                {
                    "id": "33333333-3333-3333-3333-333333333333",
                    "project_id": str(PROJECT_ID),
                    "document_id": None,
                    "created_by": "11111111-1111-1111-1111-111111111111",
                    "title": "Recently active",
                    "model": "llama3.2:latest",
                    "created_at": "2026-09-26T14:00:00Z",
                    "updated_at": "2026-09-26T14:00:00Z",
                    "activity_at": "2026-09-26T15:30:00Z",
                }
            ],
        )

    repository = SupabaseWritingStudioRepository(
        supabase_url="https://example.supabase.co",
        publishable_key="test-publishable-key",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )
    try:
        conversations = await repository.list_conversations(
            access_token="test-user-jwt",
            project_id=PROJECT_ID,
        )
    finally:
        await repository.close()

    assert [conversation.title for conversation in conversations] == ["Recently active"]
