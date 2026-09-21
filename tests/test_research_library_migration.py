from __future__ import annotations

from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "migrations"
    / "20260921225000_research_library.sql"
)


def test_research_library_tables_are_rls_scoped_and_anon_is_revoked() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert sql.count("enable row level security") == 3
    for table in ("sources", "source_versions", "source_chunks"):
        assert f"revoke all on public.{table} from anon" in sql
    assert "grant select, insert, update on public.sources to authenticated" in sql
    assert "grant select, insert, update on public.source_versions to authenticated" in sql
    assert "grant select, insert on public.source_chunks to authenticated" in sql
    assert "grant select, insert, update, delete on public.sources" not in sql
    assert "grant select, insert, update, delete on public.source_versions" not in sql


def test_source_provenance_and_processing_state_are_hardened() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "sources_preserve_provenance" in sql
    assert "source_versions_preserve_provenance" in sql
    assert "source provenance fields are immutable" in sql
    assert "source version provenance fields are immutable" in sql
    assert "source_chunks_insert_processing_version" in sql
    assert "v.status = 'processing'" in sql
    assert "idx_sources_ready_checksum_unique" in sql


def test_storage_bucket_is_private_project_scoped_and_ready_objects_are_not_deletable() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "'mi-llama-sources'" in sql
    assert "false," in sql
    assert "mi_llama_sources_select_project" in sql
    assert "mi_llama_sources_insert_project_editor" in sql
    assert "mi_llama_sources_delete_failed_processing" in sql
    assert "public.can_access_project(public.source_storage_project_id(name))" in sql
    assert "public.can_edit_project(public.source_storage_project_id(name))" in sql
    assert "v.status in ('processing', 'failed')" in sql
    assert "for update\nto authenticated" not in sql.split("on storage.objects")[-1]
