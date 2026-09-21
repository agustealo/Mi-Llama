from __future__ import annotations

from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "migrations"
    / "20260921214500_project_foundation.sql"
)


def test_supabase_migration_keeps_user_data_behind_rls() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert sql.count("enable row level security") == 5
    assert "revoke all on public.projects from anon" in sql
    assert "revoke all on public.project_members from anon" in sql
    assert "revoke all on public.conversations from anon" in sql
    assert "revoke all on public.messages from anon" in sql
    assert "revoke all on public.learning_signals from anon" in sql
    assert "owner_id uuid not null default auth.uid()" in sql
    assert "created_by uuid not null default auth.uid()" in sql
    assert "user_id uuid not null default auth.uid()" in sql
    assert "service_role" not in sql


def test_learning_signal_contract_is_explicit_and_append_only() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    for event in (
        "research_result_impression",
        "research_result_opened",
        "research_result_saved",
        "research_result_rejected",
        "source_cited",
        "source_untrusted",
        "citation_accepted",
        "citation_rejected",
        "ai_edit_accepted",
        "ai_edit_rejected",
        "research_suggestion_accepted",
        "research_suggestion_rejected",
    ):
        assert event in sql

    assert "grant select, insert on public.learning_signals to authenticated" in sql
    assert (
        "grant select, insert, update"
        not in sql.split("grant select, insert on public.learning_signals to authenticated")[0].split(
            "public.learning_signals"
        )[-1]
    )
