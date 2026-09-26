from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from mi_llama.writing_structure.models import ManuscriptRevision

MIGRATION = Path("supabase/migrations/20260926093000_structured_revision_snapshots.sql")
PROJECT_ID = UUID("11111111-1111-4111-8111-111111111111")
DOCUMENT_ID = UUID("22222222-2222-4222-8222-222222222222")
REVISION_ID = UUID("33333333-3333-4333-8333-333333333333")
USER_ID = UUID("44444444-4444-4444-8444-444444444444")


def test_revision_model_exposes_structured_editor_snapshot() -> None:
    editor_state = {
        "schema": "tiptap_v1",
        "doc": {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "Immutable formatting",
                            "marks": [{"type": "bold"}],
                        }
                    ],
                }
            ],
        },
    }
    revision = ManuscriptRevision(
        id=REVISION_ID,
        document_id=DOCUMENT_ID,
        project_id=PROJECT_ID,
        revision_number=8,
        created_by=USER_ID,
        content="Immutable formatting",
        editor_state=editor_state,
        word_count=2,
        created_at=datetime.now(UTC),
    )

    assert revision.editor_state == editor_state
    assert revision.content == "Immutable formatting"


def test_revision_model_truthfully_accepts_legacy_payload_during_rollout() -> None:
    revision = ManuscriptRevision(
        id=REVISION_ID,
        document_id=DOCUMENT_ID,
        project_id=PROJECT_ID,
        revision_number=7,
        created_by=USER_ID,
        content="Legacy immutable text",
        word_count=3,
        created_at=datetime.now(UTC),
    )

    assert revision.editor_state == {
        "schema": "plain_text_v1",
        "text": "Legacy immutable text",
    }


def test_revision_snapshot_migration_backfills_and_requires_editor_state() -> None:
    sql = MIGRATION.read_text()

    assert "add column editor_state jsonb" in sql
    assert "jsonb_build_object(" in sql
    assert "'schema', 'plain_text_v1'" in sql
    assert "'text', content" in sql
    assert "alter column editor_state set not null" in sql
    assert "manuscript_revisions_editor_state_schema_check" in sql
    assert "editor_state ->> 'schema' in ('plain_text_v1', 'tiptap_v1')" in sql
    assert "editor_state ->> 'text' = content" in sql
    assert "editor_state -> 'doc' ->> 'type' = 'doc'" in sql


def test_revision_insert_snapshots_matching_draft_or_honest_plain_text() -> None:
    sql = MIGRATION.read_text()

    assert "create or replace function public.populate_manuscript_revision_editor_state" in sql
    assert "draft.plain_text = new.content" in sql
    assert "new.editor_state := coalesce(" in sql
    assert "jsonb_build_object('schema', 'plain_text_v1', 'text', new.content)" in sql
    assert "plain-text revision state must match revision content" in sql
    assert "tiptap revision state requires a document root" in sql
    assert "before insert on public.manuscript_revisions" in sql


def test_base_revision_advance_syncs_snapshot_inside_same_transaction() -> None:
    sql = MIGRATION.read_text()

    assert "create or replace function public.sync_revision_editor_state_on_base_advance" in sql
    assert "security definer" in sql
    assert "set editor_state = new.editor_state" in sql
    assert "revision.id = new.base_revision_id" in sql
    assert "revision.project_id = new.project_id" in sql
    assert "revision.document_id = new.document_id" in sql
    assert "revision.content = new.plain_text" in sql
    assert "draft base revision does not match the committed manuscript snapshot" in sql
    assert "after update of base_revision_id on public.manuscript_drafts" in sql
    assert "when (new.base_revision_id is distinct from old.base_revision_id)" in sql


def test_revision_snapshot_helpers_are_not_directly_executable() -> None:
    sql = MIGRATION.read_text()

    assert "revoke all on function public.populate_manuscript_revision_editor_state()" in sql
    assert "revoke all on function public.sync_revision_editor_state_on_base_advance()" in sql
    assert "from authenticated;" in sql
