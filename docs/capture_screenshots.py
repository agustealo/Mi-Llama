from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE_URL = "http://127.0.0.1:8765"
SESSION_KEY = "mi-llama.supabase.session.v1"
GALLERY_DATE = "9/28/2026"
VIEWS = (
    ("overview", "01-overview.png"),
    ("library", "02-library.png"),
    ("research", "03-research.png"),
    ("notebook", "04-notebook.png"),
    ("manuscript", "05-manuscript.png"),
    ("intelligence", "06-intelligence.png"),
)


def install_authenticated_session(page: Page) -> None:
    session = {
        "access_token": "product-fixture-token",
        "refresh_token": "product-fixture-refresh",
        "expires_at": int(time.time()) + 3600,
        "token_type": "bearer",
        "user": {
            "id": "11111111-1111-1111-1111-111111111111",
            "email": "writer@mi-llama.local",
        },
    }
    key = json.dumps(SESSION_KEY)
    value = json.dumps(json.dumps(session))
    page.add_init_script(f"sessionStorage.setItem({key}, {value})")
    gallery_date = json.dumps(GALLERY_DATE)
    page.add_init_script(
        f"Date.prototype.toLocaleDateString = function () {{ return {gallery_date}; }}"
    )


def create_project(page: Page) -> None:
    page.goto(f"{BASE_URL}/#manuscript", wait_until="networkidle")
    page.get_by_role("heading", name="Create a writing project").wait_for()
    page.locator("#new-project-title").fill("Coastal Resilience Brief")
    page.get_by_role("button", name="Create project").click()
    page.get_by_role("heading", name="Create the first manuscript").wait_for()


def create_manuscript(page: Page) -> None:
    page.locator("#new-document-title").fill("Coastal Resilience Draft")
    page.get_by_role("button", name="Create manuscript").click()
    rich_host = page.locator(".rich-manuscript-editor")
    rich_host.wait_for()
    rich_editor = rich_host.locator('[contenteditable="true"]')
    rich_editor.wait_for()
    page.locator("#manuscript-consumer-bar").wait_for()
    page.get_by_role("button", name="Versions").wait_for()
    rich_editor.fill(
        "Coastal resilience planning works best when claims stay connected to reviewed evidence. "
        "This manuscript keeps source-backed edits reviewable before they become part of the draft."
    )
    page.wait_for_function(
        "() => document.querySelector('#studio-save-status')?.textContent === 'Saved'"
    )
    page.get_by_role("button", name="Save version").click()
    page.wait_for_function(
        "() => document.querySelector('#studio-save-status')?.textContent === 'Version 1 saved'"
    )
    page.get_by_text("1 saved version", exact=False).wait_for()

    page.get_by_role("button", name="Outline", exact=True).click()
    page.locator(".manuscript-outline-create input").fill("Evidence and argument")
    page.get_by_role("button", name="Add section").click()
    page.get_by_text("Evidence and argument", exact=True).wait_for()

    page.get_by_role("button", name="Details", exact=True).click()
    page.locator("#manuscript-management-panel select").select_option("review")
    page.get_by_role("button", name="Save details").click()
    page.get_by_text("Review · 1 saved version", exact=False).wait_for()

    page.get_by_role("button", name="Versions", exact=True).click()
    page.get_by_text("Version 1", exact=True).wait_for()
    page.get_by_role("button", name="Close", exact=True).click()


def upload_source(page: Page) -> None:
    page.goto(f"{BASE_URL}/#library", wait_until="networkidle")
    page.locator("#surface-source-file").set_input_files(
        {
            "name": "coastal-evidence.txt",
            "mimeType": "text/plain",
            "buffer": (
                b"Coastal wetlands reduce storm surge and support long-term resilience planning.\n"
                b"Local adaptation plans should connect infrastructure decisions "
                b"to reviewed evidence.\n"
            ),
        }
    )
    page.get_by_role("button", name="Upload source").click()
    page.get_by_text("coastal-evidence.txt", exact=True).wait_for()
    page.get_by_text("ready", exact=True).wait_for()


def add_question(page: Page) -> None:
    page.goto(f"{BASE_URL}/#research", wait_until="networkidle")
    question = "How do restored wetlands change coastal storm-surge exposure?"
    page.locator("#surface-question").fill(question)
    page.get_by_role("button", name="Add question").click()
    page.get_by_text(question, exact=True).wait_for()


def add_note(page: Page) -> None:
    page.goto(f"{BASE_URL}/#notebook", wait_until="networkidle")
    page.locator("#surface-note-title").fill("Evidence framing")
    page.locator("#surface-note-body").fill(
        "Keep adaptation claims tied to reviewed project sources and preserve counterevidence."
    )
    page.get_by_role("button", name="Add note").click()
    page.get_by_role("heading", name="Evidence framing").wait_for()


def assert_overview_truth(page: Page) -> None:
    page.goto(f"{BASE_URL}/#overview", wait_until="networkidle")
    page.get_by_role("heading", name="Coastal Resilience Brief").wait_for()
    for label in ("Sources", "Open questions", "Research notes"):
        card = page.locator(".stat", has_text=label)
        card.locator(".value").filter(has_text="1").wait_for()
    page.get_by_text("Live project status", exact=False).wait_for()


def stable_screenshot(page: Page) -> bytes:
    first = page.screenshot(full_page=True, animations="disabled", caret="hide")
    page.wait_for_timeout(100)
    second = page.screenshot(full_page=True, animations="disabled", caret="hide")
    if first != second:
        raise RuntimeError("Product screenshot is not byte-stable across consecutive captures")
    return first


def capture_views(page: Page, output: Path) -> None:
    for view, filename in VIEWS:
        page.goto(f"{BASE_URL}/#{view}", wait_until="networkidle")
        page.wait_for_timeout(250)
        (output / filename).write_bytes(stable_screenshot(page))


def main() -> None:
    output = Path(__file__).resolve().parent / "assets" / "screenshots"
    output.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--disable-gpu"])
        page = browser.new_page(
            viewport={"width": 1440, "height": 960},
            device_scale_factor=1,
        )
        page.on("console", lambda message: print(f"BROWSER {message.type}: {message.text}"))
        page.on("pageerror", lambda error: print(f"BROWSER PAGE ERROR: {error}"))
        install_authenticated_session(page)
        create_project(page)
        create_manuscript(page)
        upload_source(page)
        add_question(page)
        add_note(page)
        assert_overview_truth(page)
        capture_views(page, output)
        browser.close()

    captures = sorted(output.glob("*.png"))
    if len(captures) != len(VIEWS):
        raise RuntimeError(f"Expected {len(VIEWS)} screenshots, found {len(captures)}")


if __name__ == "__main__":
    main()
