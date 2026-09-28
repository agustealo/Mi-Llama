from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_product_gallery_uses_authenticated_fixture_and_real_api_path() -> None:
    workflow = (ROOT / ".github" / "workflows" / "product-gallery.yml").read_text()
    capture = (ROOT / "docs" / "capture_screenshots.py").read_text()
    fixture = (ROOT / "docs" / "product_fixture_server.py").read_text()

    assert "python docs/product_fixture_server.py" in workflow
    assert "docs/product_fixture_server.py" in workflow
    assert "product-fixture-token" in capture
    assert "sessionStorage.setItem" in capture
    assert ".route(" not in capture
    assert "page.route" not in capture
    assert "#new-project-title" in capture
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


def test_product_gallery_capture_is_deterministic_before_commit_comparison() -> None:
    capture = (ROOT / "docs" / "capture_screenshots.py").read_text()

    assert 'playwright.chromium.launch(args=["--disable-gpu"])' in capture
    assert 'animations="disabled"' in capture
    assert 'caret="hide"' in capture
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
