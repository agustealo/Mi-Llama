from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from mi_llama.citation_authority import (
    CitationAuthor,
    CitationProfile,
    SaveSourceCitationMetadataRequest,
    SourceCitationMetadata,
    render_citation,
)

SOURCE_ID = UUID("11111111-1111-4111-8111-111111111111")
PROJECT_ID = UUID("22222222-2222-4222-8222-222222222222")
USER_ID = UUID("33333333-3333-4333-8333-333333333333")
CITATION_ID = UUID("44444444-4444-4444-8444-444444444444")
MIGRATION = Path("supabase/migrations/20260926053000_citation_authority.sql")


def _request() -> SaveSourceCitationMetadataRequest:
    return SaveSourceCitationMetadataRequest(
        item_type="book",
        title="Evidence First",
        authors=[CitationAuthor(family="Smith", given="Jane")],
        issued_year=2026,
        publisher="Research Press",
        doi="10.1000/example",
    )


def _metadata() -> SourceCitationMetadata:
    now = datetime.now(UTC)
    return SourceCitationMetadata(
        source_id=SOURCE_ID,
        project_id=PROJECT_ID,
        created_by=USER_ID,
        updated_by=USER_ID,
        version=3,
        csl=_request().to_csl_json(source_id=SOURCE_ID),
        created_at=now,
        updated_at=now,
    )


def test_metadata_request_builds_csl_json_without_inventing_file_provenance() -> None:
    csl = _request().to_csl_json(source_id=SOURCE_ID)

    assert csl["id"] == str(SOURCE_ID)
    assert csl["type"] == "book"
    assert csl["title"] == "Evidence First"
    assert csl["author"] == [{"family": "Smith", "given": "Jane"}]
    assert csl["issued"] == {"date-parts": [[2026]]}
    assert csl["publisher"] == "Research Press"
    assert csl["DOI"] == "10.1000/example"
    assert "filename" not in csl


def test_metadata_request_rejects_partial_dates() -> None:
    with pytest.raises(ValidationError):
        SaveSourceCitationMetadataRequest(
            item_type="book",
            title="Evidence First",
            issued_month=9,
        )


@pytest.mark.parametrize(
    "style",
    [CitationProfile.APA_7, CitationProfile.MLA_9, CitationProfile.CHICAGO_AUTHOR_DATE],
)
def test_supported_profiles_render_real_csl_output(style: CitationProfile) -> None:
    rendered = render_citation(citation_id=CITATION_ID, metadata=_metadata(), style=style)

    assert rendered.metadata_version == 3
    assert rendered.source_id == SOURCE_ID
    assert rendered.style is style
    assert rendered.in_text
    assert rendered.bibliography
    assert "Smith" in rendered.in_text
    assert "Smith" in rendered.bibliography
    assert "Evidence" in rendered.bibliography


def test_citation_authority_migration_has_versioned_rls_metadata() -> None:
    sql = MIGRATION.read_text()

    assert "create table public.source_citation_metadata" in sql
    assert "version bigint not null default 1" in sql
    assert "alter table public.source_citation_metadata enable row level security" in sql
    assert "grant select on public.source_citation_metadata to authenticated" in sql
    assert "grant insert (source_id, project_id, created_by, updated_by, version, csl)" in sql
    assert "create policy source_citation_metadata_insert_editor" in sql
    assert "create policy source_citation_metadata_update_editor" in sql
    assert "security invoker" in sql
    assert "public.can_access_project(project_id)" in sql
    assert "public.can_edit_project(p_project_id)" in sql
    assert "citation metadata version is stale" in sql
    assert "citation metadata CSL id must match the source" in sql


def test_citation_insertion_is_atomic_idempotent_and_stale_fenced() -> None:
    sql = MIGRATION.read_text()

    assert "create table public.citation_insertions" in sql
    assert "citation_id uuid not null unique" in sql
    assert "create or replace function public.insert_writing_citation" in sql
    assert "security definer" in sql
    assert "caller := auth.uid()" in sql
    assert "public.can_edit_project(p_project_id)" in sql
    assert "item.id = p_insertion_id" in sql
    assert "item.citation_id = p_citation_id" in sql
    assert "target_draft.version <> p_expected_draft_version" in sql
    assert "target_metadata.version <> p_metadata_version" in sql
    assert "target_draft.plain_text is distinct from target_revision.content" in sql
    assert "from public.create_manuscript_revision" in sql
    assert "set status = 'accepted'" in sql
    assert "'citation_accepted'" in sql
    assert "'source_cited'" in sql
    assert "grant execute on function public.insert_writing_citation" in sql
