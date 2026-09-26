from pathlib import Path


def test_workspace_loads_citation_closure_assets() -> None:
    root = Path(__file__).parents[1] / "src" / "mi_llama" / "workspace_assets"
    index = (root / "index.html").read_text()

    assert 'href="studio_citation_closure.css"' in index
    assert 'src="studio_citation_closure.js"' in index


def test_citation_closure_is_read_only_and_proposal_bound() -> None:
    root = Path(__file__).parents[1] / "src" / "mi_llama" / "workspace_assets"
    script = (root / "studio_citation_closure.js").read_text()
    contract = (root / "citation_closure_contract.js").read_text()

    assert "/writing/documents/${documentId}/proposals" in script
    assert "/research/citations/${citationId}/context" in script
    assert "Nothing is inserted automatically" in script
    assert "/insert" not in script
    assert "method: 'POST'" not in script
    assert "proposal?.status === 'accepted'" in contract
    assert "manuscriptState: exact ? 'exact' : 'changed'" in contract
    assert "String(context.insertion.document_id) === String(documentId)" in contract
    assert "context?.citation?.status === 'rejected'" in contract
