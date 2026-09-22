from pathlib import Path


def test_writing_intelligence_migration_keeps_analysis_proposal_only() -> None:
    sql = Path(
        "supabase/migrations/20260922005500_writing_intelligence.sql"
    ).read_text(encoding="utf-8")

    assert "create table public.writing_analysis_runs" in sql
    assert "create table public.writing_analysis_findings" in sql
    assert "create table public.writing_finding_candidates" in sql
    assert "alter table public.writing_analysis_runs enable row level security" in sql
    assert "alter table public.writing_analysis_findings enable row level security" in sql
    assert "alter table public.writing_finding_candidates enable row level security" in sql

    assert "grant select on public.writing_analysis_runs to authenticated" in sql
    assert "grant select on public.writing_analysis_findings to authenticated" in sql
    assert "grant select on public.writing_finding_candidates to authenticated" in sql
    assert "grant insert on public.writing_analysis_findings" not in sql
    assert "grant update on public.writing_analysis_findings" not in sql
    assert "grant insert on public.writing_finding_candidates" not in sql

    assert "create or replace function public.persist_writing_analysis" in sql
    assert "security definer" in sql
    assert "project edit access required" in sql
    assert "analysis may contain at most 20 findings" in sql
    assert "a finding may contain at most 10 evidence candidates" in sql

    assert "create or replace function public.review_writing_finding" in sql
    assert "writing_finding_confirmed" in sql
    assert "writing_finding_dismissed" in sql
    assert "create or replace function public.promote_writing_finding_to_question" in sql
    assert "writing_gap_created" in sql

    assert "writing finding candidate chunk provenance is invalid" in sql
    assert "writing finding must remain inside the analyzed passage" in sql
    assert "writing analysis revision must belong to the manuscript document" in sql
