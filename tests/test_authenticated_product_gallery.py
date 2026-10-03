import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).parents[1]


def _strict_fixture_module():
    path = ROOT / "docs" / "product_fixture_strict_server.py"
    spec = importlib.util.spec_from_file_location("product_fixture_strict_server", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_product_gallery_uses_authenticated_fixture_and_real_api_path() -> None:
    workflow = (ROOT / ".github" / "workflows" / "product-gallery.yml").read_text()
    capture = (ROOT / "docs" / "capture_screenshots.py").read_text()
    fixture = (ROOT / "docs" / "product_fixture_server.py").read_text()
    strict_fixture = (ROOT / "docs" / "product_fixture_strict_server.py").read_text()

    assert "python docs/product_fixture_strict_server.py" in workflow
    assert "docs/product_fixture_strict_server.py" in workflow
    assert "docs/product_fixture_server.py" in workflow
    assert "product-fixture-token" in capture
    assert "sessionStorage.setItem" in capture
    assert ".route(" not in capture
    assert "page.route" not in capture
    assert "#new-project-title" in capture
    assert "#new-document-title" in capture
    assert ".rich-manuscript-editor" in capture
    assert '[contenteditable="true"]' in capture
    assert "#manuscript-consumer-bar" in capture
    assert "Save version" in capture
    assert "Version 1 saved" in capture
    assert "#surface-source-file" in capture
    assert "#surface-question" in capture
    assert "#surface-note-body" in capture
    assert 'label in ("Sources", "Open questions", "Research notes")' in capture
    assert capture.index("assert_overview_truth(page)") < capture.index(
        "capture_views(page, output)"
    )
    assert "create_workspace_app(" in fixture
    assert "create_api_app(" not in fixture
    assert "attach_workspace(" not in fixture
    assert "FixtureRepository()" in fixture
    assert "FixtureStorage()" in fixture
    assert "class StrictFixtureRepository(FixtureRepository)" in strict_fixture
    assert "repository=StrictFixtureRepository()" in strict_fixture
    assert "storage=FixtureStorage()" in strict_fixture


def test_product_gallery_capture_is_deterministic_before_commit_comparison() -> None:
    capture = (ROOT / "docs" / "capture_screenshots.py").read_text()

    assert 'playwright.chromium.launch(args=["--disable-gpu"])' in capture
    assert 'animations="disabled"' in capture
    assert 'caret="hide"' in capture
    assert 'GALLERY_DATE = "9/28/2026"' in capture
    assert "Date.prototype.toLocaleDateString" in capture
    assert "if first != second:" in capture
    assert "Product screenshot is not byte-stable across consecutive captures" in capture
    assert ".write_bytes(stable_screenshot(page))" in capture


def test_product_gallery_uses_a_bounded_pixel_fidelity_contract() -> None:
    workflow = (ROOT / ".github" / "workflows" / "product-gallery.yml").read_text()
    verifier = (ROOT / "docs" / "verify_product_gallery.py").read_text()

    assert "docs/verify_product_gallery.py" in workflow
    assert "python docs/verify_product_gallery.py" in workflow
    assert "git diff --exit-code -- docs/assets/screenshots" not in workflow
    assert "MAX_CHANGED_PIXELS = 64" in verifier
    assert "MAX_CHANNEL_DELTA = 12" in verifier
    assert 'subprocess.run(\n        ["git", "show"' in verifier
    assert "dimensions changed" in verifier
    assert "expected 6 governed screenshots" in verifier
    assert "Product screenshots materially differ" in verifier


def test_workspace_factory_supports_governed_dependency_injection() -> None:
    workspace = (ROOT / "src" / "mi_llama" / "workspace.py").read_text()

    assert "provider: ModelProvider | None = None" in workspace
    assert "repository: Repository | None = None" in workspace
    assert "storage: ObjectStorage | None = None" in workspace
    assert "research_engine: ResearchEngine | None = None" in workspace
    assert "provider=provider" in workspace
    assert "repository=repository" in workspace
    assert "storage=storage" in workspace
    assert "research_engine=research_engine" in workspace


def test_fixture_does_not_add_a_production_fallback() -> None:
    workspace = (ROOT / "src" / "mi_llama" / "workspace.py").read_text()
    main = (ROOT / "src" / "mi_llama" / "main.py").read_text()

    assert "product-fixture" not in workspace
    assert "product-fixture" not in main


def test_strict_fixture_supports_first_manuscript_draft_bootstrap() -> None:
    fixture = _strict_fixture_module()
    with TestClient(fixture.build_app()) as client:
        headers = {"Authorization": "Bearer product-fixture-token"}
        project_response = client.post(
            "/api/projects",
            headers=headers,
            json={"title": "Gallery manuscript", "description": None},
        )
        assert project_response.status_code == 201, project_response.text
        project_id = project_response.json()["id"]

        document_response = client.post(
            f"/api/projects/{project_id}/writing/documents",
            headers=headers,
            json={"outline_node_id": None, "title": "First manuscript"},
        )
        assert document_response.status_code == 201, document_response.text
        document_id = document_response.json()["id"]

        draft_response = client.get(
            f"/api/projects/{project_id}/writing/documents/{document_id}/draft",
            headers=headers,
        )
        assert draft_response.status_code == 200, draft_response.text
        assert draft_response.json() is None
