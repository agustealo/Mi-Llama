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
        "setAnnotations(annotations)",
        "clearAnnotations()",
        "revealRange(start, end)",
        "onChange(listener)",
        "onSelectionChange(listener)",
        "export function bindTextareaEditor",
        "export function getEditorAdapter",
        "export function documentStateForText",
    ):
        assert contract in adapter
    assert "schema: 'plain_text_v1'" in adapter


def test_tiptap_annotations_are_browser_highlights_not_document_mutations() -> None:
    adapter = (ROOT / "tiptap_adapter.js").read_text()
    annotation_section = adapter.split("setAnnotations(annotations) {", 1)[1].split(
        "\n  clearAnnotations()", 1
    )[0]

    assert "document.createRange()" in annotation_section
    assert "globalThis.CSS.highlights.set" in annotation_section
    assert "new globalThis.Highlight" in annotation_section
    assert "editor.commands" not in annotation_section
    assert "insertContent" not in annotation_section
    assert "this.clearAnnotations()" in adapter.split("onUpdate: () => {", 1)[1].split(
        "onSelectionUpdate", 1
    )[0]
    assert "this.clearAnnotations()\n    this.muted = true" in adapter
    assert "this.clearAnnotations()\n    for (const unsubscribe" in adapter


def test_manuscript_consumers_depend_on_editor_adapter_not_textarea_offsets() -> None:
    studio = (ROOT / "studio.js").read_text()
    research = (ROOT / "studio_research.js").read_text()
    citations = (ROOT / "studio_citations.js").read_text()
    intelligence = (ROOT / "studio_intelligence.js").read_text()

    assert "bindTextareaEditor" in studio
    assert "documentStateForText(text)" in studio
    assert "getEditorAdapter()" in studio
    assert "getEditorAdapter()" in research
    assert "getEditorAdapter()" in citations
    assert "getEditorAdapter()" in intelligence

    for consumer in (studio, research, citations, intelligence):
        assert "editor.selectionStart" not in consumer
        assert "editor.selectionEnd" not in consumer
        assert "editor.value" not in consumer

    assert "editor.getSelection()" in studio
    assert "editor.getSelection()" in research
    assert "editor.getSelection()" in intelligence
    assert "editor.getText() !== snapshot.fullText" in research
    assert "draft.plain_text !== editor.getText()" in citations
