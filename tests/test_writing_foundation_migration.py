from pathlib import Path


def test_writing_foundation_migration_keeps_revision_and_research_authority_in_postgres() -> None:
    sql = Path("supabase/migrations/20260921234000_writing_foundation.sql").read_text(
        encoding="utf-8"
    )

    for table in (
        "outline_nodes",
        "manuscript_documents",
        "manuscript_revisions",
        "writing_research_links",
    ):
        assert f"alter table public.{table} enable row level security" in sql
        assert f"revoke all on public.{table} from anon" in sql

    assert "create or replace function public.create_manuscript_revision" in sql
    assert "security definer" in sql
    assert "for update;" in sql
    assert "public.count_manuscript_words(p_content)" in sql
    assert "grant select on public.manuscript_revisions to authenticated" in sql
    assert "grant select, insert on public.writing_research_links to authenticated" in sql
    assert "grant update (outline_node_id, title, status)" in sql
    assert "outline hierarchy cannot contain cycles" in sql
    assert "linked citation must be accepted and belong to the same project" in sql
    assert "writing research link passage exceeds revision content" in sql
