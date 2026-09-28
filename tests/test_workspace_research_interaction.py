from pathlib import Path


def _research_script() -> str:
    return (
        Path(__file__).parents[1] / "src" / "mi_llama" / "workspace_assets" / "studio_research.js"
    ).read_text()


def test_workspace_loads_research_interaction_assets() -> None:
    root = Path(__file__).parents[1] / "src" / "mi_llama" / "workspace_assets"
    index = (root / "index.html").read_text()
    script = _research_script()

    assert 'href="studio_research.css"' in index
    assert 'src="studio_research.js"' in index
    assert "Find sources" in script
    assert "/research/query" in script
    assert "/research/promotions" in script
    assert "crypto.randomUUID()" in script
    assert "Sources to review" in script
    assert "Sources for this edit" in script
    assert "retrieval score" not in script
    assert "candidate-only" not in script
    assert "draft v${snapshot.draftVersion}" not in script
    assert "provenance repair" not in script


def test_research_promotion_does_not_drive_checkpoint_ui_or_poll_server() -> None:
    script = _research_script()

    assert "checkpoint-revision" not in script
    assert "CHECKPOINT_TIMEOUT_MS" not in script
    assert "POLL_DELAY_MS" not in script
    assert "expected_draft_version: snapshot.draftVersion" in script
    assert "window.location.reload()" in script
    assert "PROMOTION_FLASH_KEY" in script


def test_reviewed_evidence_can_form_a_bounded_multi_source_grounding_packet() -> None:
    script = _research_script()

    assert "MAX_GROUNDING_CITATIONS = 8" in script
    assert "EVIDENCE_TRAY_KEY" in script
    assert "Sources for this edit" in script
    assert "stanceSummary" in script
    assert "Find more sources for this passage" in script
    assert "citation_ids: target.citationIds" in script
    assert "citation_ids: [target.citationId]" not in script
    assert "clearEvidenceTray()" in script
    assert "The manuscript changed. Select the passage again to refresh its sources." in script


def test_evidence_tray_remains_interaction_state_not_a_second_authority() -> None:
    script = _research_script()

    assert "sessionStorage.setItem(EVIDENCE_TRAY_KEY" in script
    assert "The server remains authoritative" in script
    assert "projectId: snapshot.projectId" in script
    assert "documentId: snapshot.documentId" in script
    assert "selectionStart: snapshot.start" in script
    assert "selectionEnd: snapshot.end" in script
    assert "selectionText: snapshot.text" in script
    assert "draftVersion: result.draft.version" in script


def test_evidence_tray_is_fenced_against_stale_manuscript_state() -> None:
    script = _research_script()

    assert "editor.getText() !== snapshot.fullText" in script
    assert (
        "clearResearchState('The manuscript changed. Select the passage again "
        "to refresh its sources.', true)" in script
    )
    assert "clearEvidenceTray()" in script
    assert "The manuscript changed after this source search." in script
    assert "The saved manuscript changed after this source search." in script
    assert "draft.version !== target.draftVersion" in script
    assert (
        "draft.plain_text.slice(target.selectionStart, target.selectionEnd) "
        "!== target.selectionText" in script
    )


def test_evidence_tray_supports_removal_and_readdition_without_mutating_canonical_research() -> (
    None
):
    script = _research_script()

    assert "removeTrayCitation" in script
    assert "tray.items.filter((item) => item.citationId !== citationId)" in script
    assert "addPromotionToTray" in script
    assert "existingIndex = tray.items.findIndex" in script
    assert "tray.items[existingIndex] = item" in script
    assert "tray.items.push(item)" in script
    assert "Remove one before adding another" in script
