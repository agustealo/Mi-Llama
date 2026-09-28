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
        "Canonical data first",
        "canonical source collection",
        "provider contract",
        "Revision-bound provenance",
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


def test_workspace_chrome_starts_with_product_language() -> None:
    shell = (ASSETS / "index.html").read_text()

    assert "Writing & Research Studio" in shell
    assert "Workspace starting" in shell
    assert "Checking writing and research tools…" in shell
    assert "Sign in" in shell
    assert "Open your projects" in shell
    for phrase in ("Local runtime", "Local workspace", "No account session", "runtime status"):
        assert phrase not in shell


def test_sign_in_failures_are_translated_before_the_dialog_sees_them() -> None:
    auth = (ASSETS / "auth.js").read_text()

    assert "Email or password is incorrect." in auth
    assert "Confirm your email before signing in." in auth
    assert "Too many sign-in attempts. Try again shortly." in auth
    assert "Sign-in service is temporarily unavailable. Try again shortly." in auth
    assert "Sign-in is unavailable in this workspace." in auth
    assert "Your session has ended. Sign in again." in auth
    assert "throw new AuthError(authMessage(" in auth


def test_workspace_shell_keeps_navigation_and_health_contracts() -> None:
    script = (ASSETS / "app.js").read_text()

    for view in ("overview", "library", "research", "notebook", "manuscript", "intelligence"):
        assert f"id: '{view}'" in script
    assert "addEventListener('hashchange', render)" in script
    assert "fetch('/health'" in script
    assert "health?.provider?.available" in script
    assert "health?.research === 'ready'" in script
