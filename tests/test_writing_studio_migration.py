from pathlib import Path

MIGRATION = Path("supabase/migrations/20260925230000_writing_studio_interaction.sql")


def test_writing_studio_migration_has_mutable_draft_authority() -> None:
    sql = MIGRATION.read_text()

    assert "create table public.manuscript_drafts" in sql
    assert "document_id uuid not null unique" in sql
    assert "version bigint not null default 1" in sql
    assert "editor_state jsonb not null" in sql
    assert "plain_text text not null" in sql
    assert "new.version <> old.version + 1" in sql
    assert "alter table public.manuscript_drafts enable row level security" in sql
    assert "grant select, insert on public.manuscript_drafts to authenticated" in sql
    assert "public.can_edit_project(project_id)" in sql


def test_writing_studio_migration_has_durable_proposal_ledger() -> None:
    sql = MIGRATION.read_text()

    assert "create table public.writing_proposals" in sql
    assert "base_draft_version bigint not null" in sql
    assert "selection_hash text not null" in sql
    assert "original_text text not null" in sql
    assert "proposed_text text not null" in sql
    assert "context_manifest jsonb not null" in sql
    assert "status in ('proposed', 'accepted', 'rejected', 'stale')" in sql
    assert "alter table public.writing_proposals enable row level security" in sql
    assert "grant select, insert on public.writing_proposals to authenticated" in sql


def test_writing_proposal_acceptance_is_atomic_and_stale_fenced() -> None:
    sql = MIGRATION.read_text()

    assert "create or replace function public.apply_writing_proposal" in sql
    assert "security definer" in sql
    assert "caller := auth.uid()" in sql
    assert "public.can_edit_project(p_project_id)" in sql
    assert "for update" in sql
    assert "target_draft.version <> p_expected_draft_version" in sql
    assert "target_proposal.base_draft_version <> p_expected_draft_version" in sql
    assert "current_selection is distinct from target_proposal.original_text" in sql
    assert "p_plain_text is distinct from expected_plain_text" in sql
    assert "revoke all on function public.apply_writing_proposal" in sql
    assert "grant execute on function public.apply_writing_proposal" in sql
