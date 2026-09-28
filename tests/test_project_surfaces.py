from pathlib import Path

ASSETS = Path(__file__).parents[1] / "src" / "mi_llama" / "workspace_assets"


def test_project_surfaces_read_canonical_project_data() -> None:
    surface = (ASSETS / "studio_surfaces.js").read_text()

    for endpoint in (
        "/sources`",
        "/research/questions`",
        "/research/claims`",
        "/research/notes`",
        "/research/citations`",
    ):
        assert endpoint in surface
    assert "Promise.allSettled" in surface
    assert "emptyProjectSurfaceState" in surface
    assert "renderProjectSurface" in surface


def test_project_surfaces_replace_static_zero_state_with_live_actions() -> None:
    surface = (ASSETS / "studio_surfaces.js").read_text()

    assert 'id="surface-source-upload"' in surface
    assert 'id="surface-question-form"' in surface
    assert 'id="surface-note-form"' in surface
    assert "Upload source" in surface
    assert "Add question" in surface
    assert "Add note" in surface
    assert "Your project is private work, not example data." in surface
    assert 'data-view-target="manuscript">Create project' in surface


def test_surface_renderer_escapes_server_and_user_content() -> None:
    surface = (ASSETS / "studio_surfaces.js").read_text()

    assert "function escapeHtml(value)" in surface
    assert "escapeHtml(source.filename)" in surface
    assert "escapeHtml(item.question)" in surface
    assert "escapeHtml(note.title || 'Untitled note')" in surface
    assert "escapeHtml(textSnippet(note.body))" in surface


def test_form_data_upload_keeps_browser_multipart_boundary() -> None:
    auth = (ASSETS / "auth.js").read_text()

    assert "const bodyIsFormData = typeof FormData !== 'undefined'" in auth
    assert "options.body instanceof FormData" in auth
    assert "options.body && !bodyIsFormData && !headers.has('Content-Type')" in auth


def test_studio_owns_project_state_and_rejects_stale_surface_loads() -> None:
    studio = (ASSETS / "studio.js").read_text()

    assert "emptyProjectSurfaceState" in studio
    assert "loadProjectSurfaceState" in studio
    assert "renderProjectSurface" in studio
    assert "if (state.projectId !== projectId) return" in studio
    assert "reload: reloadProjectSurfaceState" in studio
