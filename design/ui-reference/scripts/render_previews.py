from __future__ import annotations

import base64
import mimetypes
import json
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PREV = ROOT / "previews"
PREV.mkdir(exist_ok=True)

# Render every governed product page in both themes, plus the style guide.
# SITE_MANIFEST is the authority so the render set cannot drift from page governance.
_site = json.loads((ROOT / "SITE_MANIFEST.json").read_text(encoding="utf-8"))
PAGES = [item["file"] for item in _site["pages"]] + ["style-guide.html"]


CSS = "\n".join(
    (ROOT / path).read_text(encoding="utf-8")
    for path in ("assets/tokens.css", "assets/app.css")
)


def standalone_html(path: Path, theme: str) -> str:
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    soup.html["data-theme"] = theme

    # The browser receives the document via set_content so local navigation policy
    # cannot block visual verification. Inline the shared CSS and local images.
    for tag in list(soup.find_all("link", rel="stylesheet")):
        tag.decompose()
    style = soup.new_tag("style")
    style.string = CSS
    soup.head.append(style)

    for script in list(soup.find_all("script", src=True)):
        script.decompose()
    script = soup.new_tag("script")
    script.string = (ROOT / "assets/app.js").read_text(encoding="utf-8")
    soup.body.append(script)

    for img in soup.find_all("img", src=True):
        src = img.get("src", "")
        if src.startswith(("http://", "https://", "data:")):
            continue
        local_path = (path.parent / src).resolve()
        if local_path.exists() and ROOT in local_path.parents:
            mime = mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
            data = base64.b64encode(local_path.read_bytes()).decode("ascii")
            img["src"] = f"data:{mime};base64,{data}"

    return str(soup)


def combine_themes(stem: str) -> None:
    light = Image.open(PREV / f"{stem}-light.png").convert("RGB")
    dark = Image.open(PREV / f"{stem}-dark.png").convert("RGB")
    gap = 20
    height = max(light.height, dark.height)
    canvas = Image.new("RGB", (light.width + dark.width + gap, height), (226, 231, 238))
    canvas.paste(light, (0, 0))
    canvas.paste(dark, (light.width + gap, 0))
    canvas.save(PREV / f"{stem}-theme-comparison.png")


def main() -> None:
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path="/usr/bin/chromium",
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        page = browser.new_page(viewport={"width": 1720, "height": 1080}, device_scale_factor=1)
        page.on(
            "console",
            lambda msg: errors.append(f"console {msg.type}: {msg.text}")
            if msg.type == "error"
            else None,
        )
        page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))

        for name in PAGES:
            for theme in ("light", "dark"):
                # Apply the browser preference before application initialization.
                # app.js intentionally resolves stored/preferred theme on load.
                page.emulate_media(color_scheme=theme)
                page.set_content(standalone_html(ROOT / name, theme), wait_until="load")
                actual = page.locator("html").get_attribute("data-theme")
                if actual != theme:
                    errors.append(
                        f"theme identity mismatch for {name}: requested={theme}, actual={actual}"
                    )
                page.screenshot(
                    path=str(PREV / name.replace(".html", f"-{theme}.png")),
                    full_page=True,
                )

        browser.close()

    if not errors:
        for name in PAGES:
            combine_themes(name.removesuffix(".html"))
        # Preserve the established human-facing filename for Project Home while retaining index identity.
        source = PREV / "index-theme-comparison.png"
        target = PREV / "project-home-theme-comparison.png"
        target.write_bytes(source.read_bytes())

    if errors:
        print("\n".join(errors))
        raise SystemExit(1)
    print(f"Rendered {len(PAGES) * 2} governed light/dark previews to {PREV}.")


if __name__ == "__main__":
    main()
