from pathlib import Path


def test_workspace_loads_research_interaction_assets() -> None:
    root = Path(__file__).parents[1] / "src" / "mi_llama" / "workspace_assets"
    index = (root / "index.html").read_text()
    script = (root / "studio_research.js").read_text()

    assert 'href="studio_research.css"' in index
    assert 'src="studio_research.js"' in index
    assert "Find evidence" in script
    assert "/research/query" in script
    assert "/research/promotions" in script
    assert "candidate-only" in script
    assert "crypto.randomUUID()" in script
    assert "retrieval score" in script


def test_research_promotion_does_not_drive_checkpoint_ui_or_poll_server() -> None:
    script = (
        Path(__file__).parents[1] / "src" / "mi_llama" / "workspace_assets" / "studio_research.js"
    ).read_text()

    assert "checkpoint-revision" not in script
    assert "CHECKPOINT_TIMEOUT_MS" not in script
    assert "POLL_DELAY_MS" not in script
    assert "expected_draft_version: snapshot.draftVersion" in script
    assert "window.location.reload()" in script
    assert "PROMOTION_FLASH_KEY" in script
