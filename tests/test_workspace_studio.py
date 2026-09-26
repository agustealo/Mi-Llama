from pathlib import Path

from fastapi.testclient import TestClient

from mi_llama.config import Settings
from mi_llama.workspace import create_app

ASSETS = Path(__file__).parents[1] / "src" / "mi_llama" / "workspace_assets"


def test_workspace_exposes_only_public_browser_auth_config() -> None:
    app = create_app(
        settings=Settings(
            supabase_url="https://example.supabase.co",
            supabase_publishable_key="sb_publishable_test",
            ollama_base_url="http://127.0.0.1:11434",
        )
    )

    with TestClient(app) as client:
        response = client.get("/api/client-config")

    assert response.status_code == 200
    assert response.json() == {
        "supabase_url": "https://example.supabase.co",
        "supabase_publishable_key": "sb_publishable_test",
    }


def test_workspace_loads_interactive_writing_studio_module() -> None:
    html = (ASSETS / "index.html").read_text()

    assert '<link rel="stylesheet" href="studio.css">' in html
    assert '<script type="module" src="studio.js"></script>' in html
    assert html.index('src="app.js"') < html.index('src="studio.js"')


def test_browser_auth_keeps_session_tab_scoped_and_refreshable() -> None:
    auth = (ASSETS / "auth.js").read_text()

    assert "sessionStorage" in auth
    assert "localStorage" not in auth
    assert "grant_type=password" in auth
    assert "grant_type=refresh_token" in auth
    assert "Authorization" in auth
    assert "Bearer ${token}" in auth
    assert "refresh_token" in auth


def test_studio_uses_real_draft_and_proposal_authorities() -> None:
    studio = (ASSETS / "studio.js").read_text()

    assert "/api/projects/${state.projectId}/writing/documents" in studio
    assert "/draft" in studio
    assert "/proposals" in studio
    assert "/revisions" in studio
    assert "expected_version" in studio
    assert "expected_draft_version" in studio
    assert "selectionStart" in studio
    assert "selectionEnd" in studio
    assert "Checkpoint revision" in studio
    assert "Draft changed elsewhere." in studio


def test_studio_never_synthesizes_ai_replacements_in_browser() -> None:
    studio = (ASSETS / "studio.js").read_text()

    assert "proposed_text:" not in studio
    assert "fake" not in studio.lower()
    assert "mock" not in studio.lower()
    assert "state.proposal = await apiJson" in studio
    assert "/accept`" in studio
    assert "/reject`" in studio
