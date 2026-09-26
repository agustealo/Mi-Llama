from pathlib import Path


def test_provenance_navigation_uses_editor_reveal_without_mutation() -> None:
    root = Path(__file__).parents[1] / "src" / "mi_llama" / "workspace_assets"
    script = (root / "studio_citation_closure.js").read_text()
    contract = (root / "citation_closure_contract.js").read_text()

    assert "getEditorAdapter" in script
    assert "editor.revealRange(item.manuscriptStart, item.manuscriptEnd)" in script
    assert "card.dataset.proposalId = obligation.proposalId" in script
    assert "Review citations" in script
    assert "Passage changed" in script
    assert "method: 'POST'" not in script
    assert "/insert" not in script
    assert "manuscriptStart: location.start" in contract
    assert "manuscriptEnd: location.end" in contract
    assert "return { state: 'changed', start: null, end: null }" in contract
