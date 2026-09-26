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
    assert "return 'relocated'" in contract
    assert "return 'changed'" in contract
    assert "first === draftText.lastIndexOf(proposedText)" in contract
    assert "String(context.insertion.document_id) === String(documentId)" in contract
    assert "context?.citation?.status === 'rejected'" in contract


def test_document_health_is_advisory_and_does_not_score_counterevidence() -> None:
    root = Path(__file__).parents[1] / "src" / "mi_llama" / "workspace_assets"
    script = (root / "studio_citation_closure.js").read_text()
    contract = (root / "citation_closure_contract.js").read_text()

    assert "Manuscript provenance health" in script
    assert "These are independent provenance facts, not a score." in script
    assert "Counterevidence is surfaced as research context, not treated as a defect." in script
    assert "accepted wording moved · text still matches" in script
    assert "fullyCitedEdits" in contract
    assert "openCitationEdits" in contract
    assert "changedAfterGrounding" in contract
    assert "counterevidenceEdits" in contract
    assert "item.stance === 'contradicts'" in contract
