from pathlib import Path

MIGRATION = (
    Path(__file__).parents[1]
    / "supabase"
    / "migrations"
    / "20260926150000_document_conversation_context.sql"
)


def test_document_conversation_scope_is_durable_and_immutable() -> None:
    sql = MIGRATION.read_text()

    assert "add column document_id uuid references public.manuscript_documents(id)" in sql
    assert "conversation document must belong to the same project" in sql
    assert "conversation scope and provenance are immutable" in sql
    assert "revoke update on public.conversations from authenticated" in sql
    assert "grant update (title, model) on public.conversations to authenticated" in sql


def test_message_context_is_validated_against_exact_current_draft() -> None:
    sql = MIGRATION.read_text()

    assert "add column context jsonb" in sql
    assert "document conversation user messages require manuscript context" in sql
    assert "project conversation messages cannot carry manuscript context" in sql
    assert "message context draft version is stale" in sql
    assert "message context base revision is stale" in sql
    assert "message context excerpt does not match the manuscript draft" in sql
    assert "message context hash does not match the excerpt" in sql
    assert "context_end - context_start > 16000" in sql
    assert "digest(convert_to(context_excerpt, 'UTF8'), 'sha256')" in sql
    assert "before insert on public.messages" in sql
