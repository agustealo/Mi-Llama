import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx

from mi_llama.writing_studio.repository import SupabaseWritingStudioRepository

PROJECT_ID = UUID("11111111-1111-4111-8111-111111111111")
DOCUMENT_ID = UUID("22222222-2222-4222-8222-222222222222")
DRAFT_ID = UUID("33333333-3333-4333-8333-333333333333")
USER_ID = UUID("44444444-4444-4444-8444-444444444444")
BASE_REVISION_ID = UUID("55555555-5555-4555-8555-555555555555")
MIGRATION = Path("supabase/migrations/20260926093000_structured_revision_snapshots.sql")
NOW = datetime(2026, 9, 26, 9, 25, tzinfo=UTC).isoformat()


def test_authenticated_autosave_cannot_advance_revision_ancestry() -> None:
    sql = MIGRATION.read_text()
    assert (
        "revoke update (base_revision_id) on public.manuscript_drafts from authenticated;"
        in sql
    )


def test_repository_autosave_omits_base_revision_id_from_patch() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/rest/v1/manuscript_drafts")
        assert request.method == "PATCH"
        payload = json.loads(request.content)
        seen.append(payload)
        return httpx.Response(
            200,
            json=[
                {
                    "id": str(DRAFT_ID),
                    "project_id": str(PROJECT_ID),
                    "document_id": str(DOCUMENT_ID),
                    "created_by": str(USER_ID),
                    "updated_by": str(USER_ID),
                    "base_revision_id": str(BASE_REVISION_ID),
                    "version": 5,
                    "editor_state": {"schema": "plain_text_v1", "text": "Edited text"},
                    "plain_text": "Edited text",
                    "created_at": NOW,
                    "updated_at": NOW,
                }
            ],
        )

    async def scenario() -> None:
        repository = SupabaseWritingStudioRepository(
            supabase_url="https://example.supabase.co",
            publishable_key="publishable",
            timeout_seconds=5,
            transport=httpx.MockTransport(handler),
        )
        try:
            updated = await repository.update_manuscript_draft(
                access_token="user-token",
                project_id=PROJECT_ID,
                document_id=DOCUMENT_ID,
                expected_version=4,
                base_revision_id=BASE_REVISION_ID,
                editor_state={"schema": "plain_text_v1", "text": "Edited text"},
                plain_text="Edited text",
            )
        finally:
            await repository.close()

        assert updated is not None
        assert updated.base_revision_id == BASE_REVISION_ID
        assert updated.version == 5

    asyncio.run(scenario())
    assert seen == [
        {
            "editor_state": {"schema": "plain_text_v1", "text": "Edited text"},
            "plain_text": "Edited text",
            "version": 5,
        }
    ]
