from pathlib import Path


def test_workspace_loads_provenance_repair_assets() -> None:
    root = Path(__file__).parents[1] / "src" / "mi_llama" / "workspace_assets"
    index = (root / "index.html").read_text()
    assert 'href="studio_provenance_repair.css"' in index
    assert 'src="studio_provenance_repair.js"' in index


def test_provenance_repair_preserves_proposal_authority() -> None:
    root = Path(__file__).parents[1] / "src" / "mi_llama" / "workspace_assets"
    script = (root / "studio_provenance_repair.js").read_text()
    contract = (root / "citation_closure_contract.js").read_text()

    assert "Prepare restore proposal" in script
    assert "method: 'POST'" in script
    assert "/proposals`" in script
    assert "getEditorAdapter()?.getSelection()" in script
    assert "editor.getText() !== draft.plain_text" in script
    assert "window.location.reload()" in script
    assert "citation_ids" in contract
    assert "operation: 'rewrite'" in contract
    assert "item.manuscriptState !== 'changed'" in contract
    assert "item.provenanceResolved" in contract
    assert "overwrite changed text" in script
    assert "replaceRange(" not in script
    assert "setText(" not in script


def test_provenance_disposition_is_explicit_durable_and_auditable() -> None:
    root = Path(__file__).parents[1] / "src" / "mi_llama" / "workspace_assets"
    script = (root / "studio_provenance_repair.js").read_text()

    assert "/provenance-dispositions" in script
    assert "expected_draft_version" in script
    assert "needs_regrounding" in script
    assert "retired" in script
    assert "superseded" in script
    assert "window.confirm(" in script
    assert "Resolved provenance history" in script
    assert "Frozen grounding evidence" in script
    assert "citation.content" in script
    assert "citation.content_sha256" in script
    assert "superseding_proposal_id" in script
    assert "localStorage" not in script
    assert "sessionStorage" not in script
