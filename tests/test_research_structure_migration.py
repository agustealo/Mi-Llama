from pathlib import Path


def test_research_structure_migration_locks_project_scope_and_provenance() -> None:
    sql = Path(
        "supabase/migrations/20260921230500_research_structure.sql"
    ).read_text(encoding="utf-8")

    for table in (
        "research_questions",
        "research_claims",
        "research_notes",
        "claim_evidence",
        "citation_candidates",
    ):
        assert f"create table public.{table}" in sql
        assert f"alter table public.{table} enable row level security" in sql
        assert f"revoke all on public.{table} from anon" in sql

    assert "public.can_access_project(project_id)" in sql
    assert "public.can_edit_project(project_id)" in sql
    assert "claim evidence is immutable" in sql
    assert "claim evidence source provenance is inconsistent" in sql
    assert "citation candidate must reference evidence from the same claim and project" in sql
    assert "status <> 'resolved'" in sql
    assert "grant select, insert on public.claim_evidence to authenticated" in sql
    assert "grant select, insert, update on public.citation_candidates to authenticated" in sql
    assert "grant delete" not in sql
