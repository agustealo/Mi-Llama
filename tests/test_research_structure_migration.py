from pathlib import Path


def test_research_structure_migration_locks_authority_and_provenance() -> None:
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
    assert "citation candidate provenance is immutable" in sql
    assert "status <> 'resolved'" in sql

    assert "create or replace function public.materialize_claim_evidence_effects()" in sql
    assert "after insert on public.claim_evidence" in sql
    assert "when exists (" in sql
    assert "e.stance = 'contradicts'" in sql
    assert "e.stance = 'supports'" in sql
    assert "insert into public.citation_candidates" in sql
    assert "on conflict (evidence_id) do nothing" in sql

    assert "grant select, insert on public.research_claims to authenticated" in sql
    assert "grant select, insert on public.claim_evidence to authenticated" in sql
    assert "grant select, update on public.citation_candidates to authenticated" in sql
    assert "grant select, insert, update on public.research_claims" not in sql
    assert "grant select, insert, update on public.citation_candidates" not in sql
    assert "citation_candidates_insert_editor" not in sql
    assert "grant delete" not in sql
