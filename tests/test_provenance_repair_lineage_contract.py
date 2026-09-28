from pathlib import Path


def test_grounded_repair_lineage_is_server_validated_and_frozen() -> None:
    root = Path(__file__).parents[1] / "src" / "mi_llama"
    grounding = (root / "writing_studio" / "proposal_grounding.py").read_text()
    contract = (root / "workspace_assets" / "citation_closure_contract.js").read_text()

    assert "repair_of_proposal_id: UUID | None = None" in grounding
    assert "get_writing_proposal(" in grounding
    assert "WritingProposalStatus.ACCEPTED" in grounding
    assert 'repair_grounding = repair_of.context_manifest.get("grounding")' in grounding
    assert 'context_manifest["provenance_repair"]' in grounding
    assert '"repair_of_proposal_id": str(repair_of.id)' in grounding
    assert "repair_of_proposal_id: item.proposalId" in contract


def test_supersession_ui_requires_exact_accepted_repair_lineage() -> None:
    root = Path(__file__).parents[1] / "src" / "mi_llama" / "workspace_assets"
    repair = (root / "studio_provenance_repair.js").read_text()
    contract = (root / "citation_closure_contract.js").read_text()

    assert "repairLineageProposal(item, proposals)" in repair
    assert "exactReplacement.id" in repair
    assert "Mark as replaced" in repair
    assert "superseding grounded proposal" not in repair.lower()
    assert "Record exact supersession" not in repair
    assert "proposal?.status === 'accepted'" in contract
    assert (
        "proposal?.context_manifest?.provenance_repair?.repair_of_proposal_id === item.proposalId"
        in contract
    )
