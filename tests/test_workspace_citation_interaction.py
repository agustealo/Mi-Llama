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
    assert "crypto.randomUUID()" in script
    assert "window.location.reload()" in script
