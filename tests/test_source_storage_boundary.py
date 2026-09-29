from pathlib import Path

ROOT = Path(__file__).parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "20260928205000_source_storage_boundary.sql"


def test_source_storage_insert_requires_canonical_processing_version() -> None:
    sql = MIGRATION.read_text()

    assert "drop policy if exists mi_llama_sources_insert_project_editor" in sql
    assert "create policy mi_llama_sources_insert_project_editor" in sql
    assert "bucket_id = 'mi-llama-sources'" in sql
    assert "public.can_edit_project(public.source_storage_project_id(name))" in sql
    assert "from public.source_versions v" in sql
    assert "join public.sources s" in sql
    assert "v.storage_path = storage.objects.name" in sql
    assert "v.project_id = public.source_storage_project_id(storage.objects.name)" in sql
    assert "v.status = 'processing'" in sql
    assert "s.status = 'processing'" in sql


def test_source_service_creates_version_before_storage_upload() -> None:
    source_service = (ROOT / "src" / "mi_llama" / "sources.py").read_text()

    create_version = source_service.index("await self._repository.create_source_version(")
    upload = source_service.index("await self._storage.upload(")

    assert create_version < upload
