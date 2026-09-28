from pathlib import Path

ASSETS = Path(__file__).parents[1] / "src" / "mi_llama" / "workspace_assets"


def test_workspace_shell_uses_writer_facing_language() -> None:
    script = (ASSETS / "app.js").read_text()

    assert "Evidence Review" in script
    assert "Save version" in script
    assert "Review manuscript" in script
    assert "Project source search" in script
    assert "Sources to review" in script
    assert "Workspace ready" in script


def test_workspace_shell_hides_provider_storage_and_architecture_jargon() -> None:
    script = (ASSETS / "app.js").read_text()

    forbidden = (
        "Canonical workflow",
        "canonical source collection",
        "Ollama model runtime",
        "Ollama ready",
        "Ollama unavailable",
        "Supabase authority",
        "Supabase canonical record",
        "Supabase session required",
        "RLS",
        "MindsDB research index",
        "MindsDB hybrid retrieval",
        "Private Supabase Storage + Postgres",
        "Derived MindsDB knowledge base",
        "Ingestion contract",
        "Immutable provenance",
        "Candidate discovery",
        "Candidate only",
        "pending citation candidates",
        "immutable revisions",
        "immutable revision",
        "character range",
        "Revision integrity",
        "deterministic product logic",
        "Review contract",
        "Bounded claim extraction",
        "Project-scoped retrieval",
        "Deterministic finding",
        "Explicit promotion",
        "canonical evidence",
        "product authority",
        "Local runtime connected",
        "Workspace shell · waiting for API runtime",
    )
    for phrase in forbidden:
        assert phrase not in script


def test_workspace_shell_keeps_navigation_and_health_contracts() -> None:
    script = (ASSETS / "app.js").read_text()

    for view in ("overview", "library", "research", "notebook", "manuscript", "intelligence"):
        assert f"id: '{view}'" in script
    assert "addEventListener('hashchange', render)" in script
    assert "fetch('/health'" in script
    assert "health?.provider?.available" in script
    assert "health?.research === 'ready'" in script
