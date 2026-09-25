from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8765"
VIEWS = (
    ("overview", "01-overview.png"),
    ("library", "02-library.png"),
    ("research", "03-research.png"),
    ("notebook", "04-notebook.png"),
    ("manuscript", "05-manuscript.png"),
    ("intelligence", "06-intelligence.png"),
)


def main() -> None:
    output = Path(__file__).resolve().parent / "assets" / "screenshots"
    output.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1440, "height": 960},
            device_scale_factor=1,
        )
        for view, filename in VIEWS:
            page.goto(f"{BASE_URL}/#{view}", wait_until="networkidle")
            page.wait_for_timeout(250)
            page.screenshot(path=str(output / filename), full_page=True)
        browser.close()

    captures = sorted(output.glob("*.png"))
    if len(captures) != len(VIEWS):
        raise RuntimeError(f"Expected {len(VIEWS)} screenshots, found {len(captures)}")


if __name__ == "__main__":
    main()
