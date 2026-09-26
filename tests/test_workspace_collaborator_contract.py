from pathlib import Path

ROOT = Path(__file__).parents[1] / "src" / "mi_llama" / "workspace_assets"


def test_collaborator_is_loaded_as_a_shipped_workspace_surface() -> None:
    index = (ROOT / "index.html").read_text()
    collaborator = (ROOT / "studio_collaborator.js").read_text()
    styles = (ROOT / "studio_collaborator.css").read_text()

    assert 'href="studio_collaborator.css"' in index
    assert 'src="studio_collaborator.js"' in index
    assert "collaborator-tabs" in styles
    assert "collaborator-messages" in styles
    assert "collaborator-composer" in styles
    assert "Discuss" in collaborator
    assert "Propose" in collaborator


def test_discussion_uses_document_conversations_without_manuscript_mutation() -> None:
    collaborator = (ROOT / "studio_collaborator.js").read_text()

    assert "getEditorAdapter()" in collaborator
    assert "/writing/documents/${context.documentId}/conversations" in collaborator
    assert "/api/conversations/${conversationId}" in collaborator
    assert "draft_version: draft.version" in collaborator
    assert "character_start: start" in collaborator
    assert "character_end: end" in collaborator
    assert "context.editor.getText() !== (draft.plain_text || '')" in collaborator
    assert "drainNdjsonBuffer" in collaborator
    assert "event.type === 'token'" in collaborator
    assert "event.type === 'done'" in collaborator
    assert "event.type === 'error'" in collaborator

    assert "/proposals/" not in collaborator
    assert "editor.replaceRange" not in collaborator
    assert "editor.selectionStart" not in collaborator
    assert "editor.selectionEnd" not in collaborator
    assert "innerHTML = message" not in collaborator


def test_discussion_requires_selection_for_large_drafts() -> None:
    collaborator = (ROOT / "studio_collaborator.js").read_text()

    assert "MAX_CONTEXT_CHARS = 16_000" in collaborator
    assert "This draft is too long for whole-manuscript context" in collaborator
    assert "Select at most ${MAX_CONTEXT_CHARS.toLocaleString()} characters" in collaborator
    assert "The selected passage no longer matches the saved manuscript draft." in collaborator
