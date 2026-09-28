from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_product_gallery_uses_authenticated_fixture_and_real_api_path() -> None:
    workflow = (ROOT / ".github" / "workflows" / "product-gallery.yml").read_text()
    capture = (ROOT / "docs" / "capture_screenshots.py").read_text()
    fixture = (ROOT / "docs" / "product_fixture_server.py").read_text()

    assert "python docs/product_fixture_server.py" in workflow
    assert "docs/product_fixture_server.py" in workflow
    assert "product-fixture-token" in capture
    assert "#new-project-title" in capture
    assert "#surface-source-file" in capture
    assert "#surface-question" in capture
    assert "#surface-note-body" in capture
    assert 'label in ("Sources", "Open questions", "Research notes")' in capture
    assert "create_api_app(" in fixture
    assert "attach_workspace(app)" in fixture
    assert "FixtureRepository()" in fixture
    assert "FixtureStorage()" in fixture


def test_fixture_does_not_add_a_production_fallback() -> None:
    workspace = (ROOT / "src" / "mi_llama" / "workspace.py").read_text()
    main = (ROOT / "src" / "mi_llama" / "main.py").read_text()

    assert "product-fixture" not in workspace
    assert "product-fixture" not in main
