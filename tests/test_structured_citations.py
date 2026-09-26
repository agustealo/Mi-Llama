from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from mi_llama.citation_authority import CitationPreview, CitationProfile
from mi_llama.structured_citations import (
    StructuredCitationInsertionRequest,
    build_citation_insertion_plan,
)
from mi_llama.writing_structure.models import (
    ManuscriptRevision,
    WritingResearchLink,
    WritingResearchLinkKind,
)
from mi_llama.writing_studio.models import ManuscriptDraft

PROJECT_ID = UUID("11111111-1111-4111-8111-111111111111")
DOCUMENT_ID = UUID("22222222-2222-4222-8222-222222222222")
REVISION_ID = UUID("33333333-3333-4333-8333-333333333333")
CITATION_ID = UUID("44444444-4444-4444-8444-444444444444")
SOURCE_ID = UUID("55555555-5555-4555-8555-555555555555")
USER_ID = UUID("66666666-6666-4666-8666-666666666666")
EVIDENCE_ID = UUID("77777777-7777-4777-8777-777777777777")
MIGRATION = Path("supabase/migrations/20260926081500_structured_citation_mutation.sql")


def _now() -> datetime:
    return datetime.now(UTC)


def _draft(text: str) -> ManuscriptDraft:
    now = _now()
    return ManuscriptDraft(
        id=uuid4(),
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        created_by=USER_ID,
        updated_by=USER_ID,
        base_revision_id=REVISION_ID,
        version=4,
        editor_state={"schema": "plain_text_v1", "text": text},
        plain_text=text,
        created_at=now,
        updated_at=now,
    )


def _revision(text: str) -> ManuscriptRevision:
    return ManuscriptRevision(
        id=REVISION_ID,
        document_id=DOCUMENT_ID,
        project_id=PROJECT_ID,
        revision_number=7,
        created_by=USER_ID,
        content=text,
        editor_state={"schema": "plain_text_v1", "text": text},
        word_count=2,
        created_at=_now(),
    )


def _link(text: str) -> WritingResearchLink:
    return WritingResearchLink(
        id=uuid4(),
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        revision_id=REVISION_ID,
        created_by=USER_ID,
        kind=WritingResearchLinkKind.EVIDENCE,
        entity_id=EVIDENCE_ID,
        character_start=0,
        character_end=len(text),
        created_at=_now(),
    )


def _preview() -> CitationPreview:
    return CitationPreview(
        citation_id=CITATION_ID,
        source_id=SOURCE_ID,
        metadata_version=3,
        style=CitationProfile.APA_7,
        in_text="(Smith, 2026)",
        bibliography="Smith, J. (2026). Evidence First.",
    )


def test_insertion_plan_mirrors_sql_and_places_citation_before_terminal_punctuation() -> None:
    text = "Evidence matters."
    plan, result = build_citation_insertion_plan(
        citation_id=CITATION_ID,
        source_id=SOURCE_ID,
        metadata_version=3,
        style=CitationProfile.APA_7,
        draft=_draft(text),
        revision=_revision(text),
        evidence_link=_link(text),
        rendered=_preview(),
    )

    assert result == "Evidence matters (Smith, 2026)."
    assert plan.insertion_position == len(text) - 1
    assert plan.fragment == " (Smith, 2026)"
    assert result[plan.citation_start : plan.citation_end] == "(Smith, 2026)"
    assert plan.expected_draft_version == 4
    assert plan.base_revision_id == REVISION_ID
    assert plan.evidence_revision_id == REVISION_ID
    assert len(plan.current_plain_text_sha256) == 64
    assert len(plan.resulting_plain_text_sha256) == 64


def test_structured_citation_request_requires_editor_projection_to_match_plain_text() -> None:
    text = "Evidence matters (Smith, 2026)."
    matching_state = {
        "schema": "tiptap_v1",
        "doc": {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": text}],
                }
            ],
        },
    }
    request = StructuredCitationInsertionRequest(
        insertion_id=uuid4(),
        expected_draft_version=4,
        metadata_version=3,
        style=CitationProfile.APA_7,
        editor_state=matching_state,
        plain_text=text,
    )
    assert request.editor_state["schema"] == "tiptap_v1"

    with pytest.raises(ValidationError, match="projection"):
        StructuredCitationInsertionRequest(
            insertion_id=uuid4(),
            expected_draft_version=4,
            metadata_version=3,
            style=CitationProfile.APA_7,
            editor_state=matching_state,
            plain_text="Different text",
        )


def test_structured_citation_migration_has_one_core_authority_and_legacy_wrapper() -> None:
    sql = MIGRATION.read_text()

    assert "create or replace function public.insert_writing_citation_core" in sql
    assert "create or replace function public.insert_writing_citation(" in sql
    assert "create or replace function public.insert_writing_citation_structured" in sql
    assert "structured citation plain text does not match canonical insertion" in sql
    assert "structured citation requires an existing tiptap_v1 manuscript draft" in sql
    assert "target_draft.editor_state is distinct from p_editor_state" in sql
    assert "else p_editor_state" in sql
    assert "from public.insert_writing_citation_core" in sql
    assert "grant execute on function public.insert_writing_citation_structured" in sql
    assert "from authenticated;" in sql
