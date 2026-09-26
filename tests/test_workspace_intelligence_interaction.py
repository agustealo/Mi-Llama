from pathlib import Path

ASSETS = Path(__file__).parents[1] / "src" / "mi_llama" / "workspace_assets"


def test_workspace_loads_manuscript_intelligence_after_editor_interactions() -> None:
    html = (ASSETS / "index.html").read_text()

    assert '<link rel="stylesheet" href="studio_intelligence.css">' in html
    assert '<script type="module" src="studio_intelligence.js"></script>' in html
    assert html.index('src="studio.js"') < html.index('src="studio_intelligence.js"')
    assert html.index('src="studio_research.js"') < html.index('src="studio_intelligence.js"')


def test_intelligence_analysis_is_checkpoint_bound_and_never_silent_checkpointing() -> None:
    interaction = (ASSETS / "studio_intelligence.js").read_text()

    assert "draft.base_revision_id" in interaction
    assert "revision.content !== draft.plain_text" in interaction
    assert "editorText !== draft.plain_text" in interaction
    assert "Checkpoint this manuscript before running writing intelligence." in interaction
    assert "draft/checkpoint" not in interaction
    assert "revision_id: checkpoint.revision.id" in interaction
    assert "character_start" in interaction
    assert "character_end" in interaction


def test_intelligence_review_uses_canonical_analysis_and_finding_authorities() -> None:
    interaction = (ASSETS / "studio_intelligence.js").read_text()

    assert "/analysis`" in interaction
    assert "/evidence-coverage`" in interaction
    assert "/findings/${findingId}`" in interaction
    assert "/research-question`" in interaction
    assert "status === 'proposed'" not in interaction
    assert "item.finding.status !== 'proposed'" in interaction
    assert "confidence" not in interaction.lower()
    assert "retrieval score" not in interaction.lower()


def test_intelligence_installer_is_idempotent_against_its_mutation_observer() -> None:
    interaction = (ASSETS / "studio_intelligence.js").read_text()

    guard = "key === intelligenceState.loadedKey"
    assert guard in interaction
    assert "context.editor === boundEditor" in interaction
    assert "MutationObserver" in interaction
    assert "else {\n    renderIntelligence()" not in interaction
