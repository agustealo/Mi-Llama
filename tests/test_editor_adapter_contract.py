from pathlib import Path

ROOT = Path(__file__).parents[1] / "src" / "mi_llama" / "workspace_assets"


def test_editor_adapter_owns_plain_text_editor_contract() -> None:
    adapter = (ROOT / "editor_adapter.js").read_text()

    for contract in (
        "getText()",
        "setText(text)",
        "getSelection()",
        "getDocumentState()",
        "setReadOnly(readOnly)",
        "replaceRange(start, end, replacement)",
        "onChange(listener)",
        "onSelectionChange(listener)",
        "export function bindTextareaEditor",
        "export function getEditorAdapter",
        "export function documentStateForText",
    ):
        assert contract in adapter
    assert "schema: 'plain_text_v1'" in adapter


def test_manuscript_consumers_depend_on_editor_adapter_not_textarea_offsets() -> None:
    studio = (ROOT / "studio.js").read_text()
    research = (ROOT / "studio_research.js").read_text()
    citations = (ROOT / "studio_citations.js").read_text()

    assert "bindTextareaEditor" in studio
    assert "documentStateForText(text)" in studio
    assert "getEditorAdapter()" in studio
    assert "getEditorAdapter()" in research
    assert "getEditorAdapter()" in citations

    for consumer in (studio, research, citations):
        assert "editor.selectionStart" not in consumer
        assert "editor.selectionEnd" not in consumer
        assert "editor.value" not in consumer

    assert "editor.getSelection()" in studio
    assert "editor.getSelection()" in research
    assert "editor.getText() !== snapshot.fullText" in research
    assert "draft.plain_text !== editor.getText()" in citations
