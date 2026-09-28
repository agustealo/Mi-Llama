from pathlib import Path


def test_workspace_loads_citation_authority_assets() -> None:
    root = Path(__file__).parents[1] / "src" / "mi_llama" / "workspace_assets"
    index = (root / "index.html").read_text()
    script = (root / "studio_citations.js").read_text()

    assert 'href="studio_citations.css"' in index
    assert 'src="studio_citations.js"' in index
    assert "Citation review" in script
    assert "/citation-metadata" in script
    assert "/research/citations/${citation.id}/context" in script
    assert "/research/citations/${state.activeContext.citation.id}/preview" in script
    assert "/citations/${state.activeContext.citation.id}/insert" in script
    assert "Skip citation" in script
    assert "status: 'rejected'" in script
    assert "crypto.randomUUID()" in script
    assert "window.location.reload()" in script


def test_citation_ui_hides_internal_identity_and_version_vocabulary() -> None:
    root = Path(__file__).parents[1] / "src" / "mi_llama" / "workspace_assets"
    script = (root / "studio_citations.js").read_text()

    assert "Review source details" in script
    assert "Save details & preview" in script
    assert "Insert citation" in script
    assert "saved to manuscript" in script
    assert "versioned bibliographic metadata" not in script
    assert "immutable manuscript checkpoint created" not in script
    assert "Candidate ${" not in script
    assert "linked candidate" not in script
    assert "metadata v${" not in script
    assert "Loading citation provenance" not in script
    assert "new authoritative state" not in script
