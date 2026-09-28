from pathlib import Path

ASSETS = Path(__file__).parents[1] / "src" / "mi_llama" / "workspace_assets"


def test_workspace_shell_uses_writer_facing_language() -> None:
    script = (ASSETS / "app.js").read_text()

    assert "Evidence Review" in script
    assert "Save version" in script
    assert "Open manuscript" in script
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


def test_dynamic_access_states_are_consumer_safe() -> None:
    auth = (ASSETS / "auth.js").read_text()
    studio = (ASSETS / "studio.js").read_text()

    assert "export const SIGN_IN_UNAVAILABLE = 'Sign-in is unavailable in this workspace.'" in auth
    assert "SIGN_IN_UNAVAILABLE" in studio
    assert "errorNode.textContent = unavailable ? SIGN_IN_UNAVAILABLE : ''" in studio
    assert "email.disabled = unavailable" in studio
    assert "password.disabled = unavailable" in studio
    assert "submit.disabled = unavailable" in studio
    assert "if (!state.auth) {" in studio
    assert "errorNode.textContent = SIGN_IN_UNAVAILABLE" in studio
    assert (
        "detail.textContent = state.authError ? 'Sign-in unavailable' : 'Open your projects'"
        in studio
    )
    assert "title.textContent = 'Signed in'" in studio
    assert "Sign in unavailable" in studio
    assert "new AuthError(SIGN_IN_UNAVAILABLE, 503)" in studio
    assert "state.authError = SIGN_IN_UNAVAILABLE" in studio
    for phrase in (
        "Auth unavailable",
        "Authentication is not configured",
        "Authentication configuration unavailable",
    ):
        assert phrase not in studio


def test_feature_modules_share_sign_in_unavailable_contract() -> None:
    auth = (ASSETS / "auth.js").read_text()
    studio = (ASSETS / "studio.js").read_text()

    assert "export const SIGN_IN_UNAVAILABLE = 'Sign-in is unavailable in this workspace.'" in auth
    assert "const SIGN_IN_UNAVAILABLE =" not in studio
    assert "SIGN_IN_UNAVAILABLE" in studio
    for filename in ("studio_research.js", "studio_citations.js", "studio_intelligence.js"):
        module = (ASSETS / filename).read_text()
        assert "SIGN_IN_UNAVAILABLE" in module
        assert "Authentication is not configured" not in module
        assert "new AuthError(SIGN_IN_UNAVAILABLE, 503)" in module


def test_writing_model_availability_is_capability_facing() -> None:
    studio = (ASSETS / "studio.js").read_text()

    assert 'Writing model<select id="studio-model"' in studio
    assert "Writing assistance unavailable" in studio
    assert "AI editing will return when a writing model is available." in studio
    assert "state.canEdit && writingAvailable" in studio
    assert "!selection.text.trim() || !state.model || !state.canEdit" in studio
    assert "Writing assistance is unavailable right now." in studio
    for phrase in (
        "No Ollama models available",
        "No Ollama model is available for writing proposals.",
    ):
        assert phrase not in studio


def test_api_errors_are_translated_before_reaching_writer_flows() -> None:
    auth = (ASSETS / "auth.js").read_text()
    studio = (ASSETS / "studio.js").read_text()

    assert "export function apiErrorMessage(status)" in auth
    assert "function apiErrorMessage(status)" not in studio
    assert "apiErrorMessage(response.status)" in auth
    assert "apiErrorMessage, AuthClient, AuthError" in studio
    assert "Your session has ended. Sign in again." in auth
    assert "You do not have access to do that in this project." in auth
    assert "That item is no longer available. Refresh and try again." in auth
    assert "This changed since you opened it. Review the latest version and try again." in auth
    assert "Too many requests right now. Try again shortly." in auth
    assert "Mi-Llama could not complete that right now. Try again shortly." in auth
    assert "throw new AuthError(apiErrorMessage(response.status), response.status)" in auth
    assert "Request failed (${response.status})" not in auth
    assert "payload?.detail" not in studio
    assert "Request failed (${response.status})" not in studio


def test_workspace_shell_keeps_navigation_and_health_contracts() -> None:
    script = (ASSETS / "app.js").read_text()

    for view in ("overview", "library", "research", "notebook", "manuscript", "intelligence"):
        assert f"id: '{view}'" in script
    assert "addEventListener('hashchange', render)" in script
    assert "fetch('/health'" in script
    assert "health?.provider?.available" in script
    assert "health?.research === 'ready'" in script


def test_static_shell_actions_are_owned_or_removed() -> None:
    app = (ASSETS / "app.js").read_text()

    assert 'data-view-target="manuscript">Continue writing' in app
    assert 'data-view-target="manuscript">Open manuscript' in app
    assert "closest('[data-view-target]')" in app
    assert "location.hash = view" in app
    for dead_label in (
        "Project settings",
        "Filter",
        "Upload source",
        "Research gaps",
        "New question",
        "Sort",
        "New note",
        "Review history",
    ):
        assert f">{dead_label}<" not in app


def test_source_backed_generation_uses_capability_language() -> None:
    research = (ASSETS / "studio_research.js").read_text()

    assert "Select an available writing model before generating a source-backed edit." in research
    assert (
        "Select an available Ollama model before generating a source-backed edit." not in research
    )
