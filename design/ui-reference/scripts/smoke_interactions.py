from __future__ import annotations

from pathlib import Path
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def inline_page(name: str) -> str:
    soup = BeautifulSoup((ROOT / name).read_text(encoding="utf-8"), "html.parser")
    for tag in list(soup.find_all("link", rel="stylesheet")):
        tag.decompose()
    style = soup.new_tag("style")
    style.string = (ROOT / "assets/tokens.css").read_text(encoding="utf-8") + "\n" + (ROOT / "assets/app.css").read_text(encoding="utf-8")
    soup.head.append(style)
    for tag in list(soup.find_all("script", src=True)):
        tag.decompose()
    script = soup.new_tag("script")
    script.string = (ROOT / "assets/app.js").read_text(encoding="utf-8")
    soup.body.append(script)
    return str(soup)


def main() -> None:
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.set_content(inline_page("index.html"), wait_until="load")

        initial_theme = page.locator("html").get_attribute("data-theme")
        page.locator("[data-theme-toggle]").click()
        changed_theme = page.locator("html").get_attribute("data-theme")
        page.locator("[data-workflow-select]").select_option("empirical-study-to-article")
        page.wait_for_timeout(100)
        workflow_steps = page.locator("[data-workflow-nav] .workflow-nav-step").count()
        workflow_text = page.locator("[data-workflow-nav]").inner_text()
        page.locator("[data-sidebar-toggle]").click()
        sidebar_collapsed = page.locator("body").evaluate("el => el.classList.contains('sidebar-collapsed')")

        page.set_content(inline_page("search-studio.html"), wait_until="load")
        page.locator("[data-toast]").first.click()
        page.wait_for_timeout(100)
        toast_text = page.locator(".mock-toast").inner_text()
        browser.close()

    if errors:
        raise SystemExit("Browser errors: " + "; ".join(errors))
    if initial_theme == changed_theme:
        raise SystemExit("Theme toggle did not change the active theme.")
    if not sidebar_collapsed:
        raise SystemExit("Sidebar control did not collapse the navigation.")
    if not toast_text:
        raise SystemExit("Mock action did not create user feedback.")
    if workflow_steps != 14 or "Study Design Studio" not in workflow_text or "Technical Reports & Results" not in workflow_text or "Reviewer Simulation" not in workflow_text or "Publication Audit" not in workflow_text:
        raise SystemExit("Use-case switching did not produce the ordered empirical-study-to-article workflow.")
    print("Interaction smoke test passed: theme, sidebar, mock feedback, and adaptive workflow navigation.")


if __name__ == "__main__":
    main()
