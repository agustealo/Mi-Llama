from pathlib import Path

import pytest
from pydantic import ValidationError

from mi_llama.editor_state import EditorStateError, project_editor_state, validate_editor_state
from mi_llama.writing_studio.models import SaveManuscriptDraftRequest

MIGRATION = Path("supabase/migrations/20260926073000_structured_editor_contract.sql")


def test_plain_text_state_projects_exactly() -> None:
    state = {"schema": "plain_text_v1", "text": "First paragraph.\n\nSecond paragraph."}

    assert project_editor_state(state) == "First paragraph.\n\nSecond paragraph."
    validate_editor_state(state, "First paragraph.\n\nSecond paragraph.")


def test_tiptap_state_has_deterministic_plain_text_projection() -> None:
    state = {
        "schema": "tiptap_v1",
        "doc": {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": [{"type": "text", "text": "Evidence First"}],
                },
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Strong", "marks": [{"type": "bold"}]},
                        {"type": "text", "text": " claims need sources."},
                        {"type": "hardBreak"},
                        {"type": "text", "text": "Writers stay in control."},
                    ],
                },
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Find evidence"}],
                                }
                            ],
                        },
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Review citation"}],
                                }
                            ],
                        },
                    ],
                },
            ],
        },
    }

    assert project_editor_state(state) == (
        "Evidence First\n\n"
        "Strong claims need sources.\nWriters stay in control.\n\n"
        "Find evidence\nReview citation"
    )


def test_tiptap_projection_rejects_unknown_nodes_and_marks() -> None:
    with pytest.raises(EditorStateError, match="Unsupported Tiptap block node"):
        project_editor_state(
            {
                "schema": "tiptap_v1",
                "doc": {"type": "doc", "content": [{"type": "table", "content": []}]},
            }
        )

    with pytest.raises(EditorStateError, match="Unsupported Tiptap mark"):
        project_editor_state(
            {
                "schema": "tiptap_v1",
                "doc": {
                    "type": "doc",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "No mystery marks",
                                    "marks": [{"type": "rainbow"}],
                                }
                            ],
                        }
                    ],
                },
            }
        )


def test_draft_request_rejects_editor_plain_text_split_brain() -> None:
    with pytest.raises(ValidationError, match="projection does not match"):
        SaveManuscriptDraftRequest(
            expected_version=1,
            editor_state={"schema": "plain_text_v1", "text": "Old text"},
            plain_text="Different text",
        )


def test_structured_editor_migration_allows_format_upgrade_but_blocks_destructive_downgrade() -> (
    None
):
    sql = MIGRATION.read_text()

    assert "new_schema not in ('plain_text_v1', 'tiptap_v1')" in sql
    assert "plain-text editor state must match manuscript plain text" in sql
    assert "old_schema is distinct from new_schema" in sql
    assert "old.plain_text is distinct from new.plain_text" in sql
    assert "editor schema migration must preserve canonical manuscript text" in sql
    assert "manuscript draft version must advance exactly once" in sql
