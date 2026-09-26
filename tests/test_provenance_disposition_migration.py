from pathlib import Path


MIGRATION = (
    Path(__file__).parents[1]
    / "supabase"
    / "migrations"
    / "20260926213000_provenance_dispositions.sql"
)


def test_provenance_dispositions_are_append_only_and_project_scoped() -> None:
    sql = MIGRATION.read_text()
    assert "create table public.provenance_dispositions" in sql
    assert "alter table public.provenance_dispositions enable row level security" in sql
    assert "grant select, insert on public.provenance_dispositions to authenticated" in sql
    assert "grant update" not in sql
    assert "grant delete" not in sql
    assert "public.can_access_project(project_id)" in sql
    assert "public.can_edit_project(project_id)" in sql


def test_provenance_disposition_is_revision_fenced_and_grounded() -> None:
    sql = MIGRATION.read_text()
    assert "if current_version <> new.draft_version" in sql
    assert "target_proposal.status <> 'accepted'" in sql
    assert (
        "jsonb_array_length(target_proposal.context_manifest->'grounding'->'citations') = 0" in sql
    )
    assert "replacement.status <> 'accepted'" in sql
    assert "replacement.base_draft_version <= target_proposal.base_draft_version" in sql
    assert "superseding proposal must be accepted after the historical proposal" in sql


def test_provenance_disposition_has_bounded_semantics_and_idempotency() -> None:
    sql = MIGRATION.read_text()
    assert "disposition in ('retired', 'superseded', 'needs_regrounding')" in sql
    assert "idx_provenance_dispositions_idempotent" in sql
    assert "disposition = 'superseded' and superseding_proposal_id is not null" in sql
    assert "disposition <> 'superseded' and superseding_proposal_id is null" in sql
