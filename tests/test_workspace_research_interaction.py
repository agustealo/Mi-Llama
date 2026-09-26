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
