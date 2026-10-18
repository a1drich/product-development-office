"""`office shoot`: screenshots and UX checks of a running app, driven by docs/manual/pages.json.

This is the fallback for repos without their own screenshot command. A repo's own
`make screenshots` is preferred, since setting up states such as "empty" or "validation
error" needs knowledge of the app. Fields this runner doesn't know are ignored.

The target repo lists the pages of its user manual in `docs/manual/pages.json`:

    {
      "pages": [
        {"name": "home", "path": "/", "title": "Home", "expect": "Notes"},
        {"name": "home-empty", "path": "/?demo=empty", "title": "Home, no notes yet"}
      ]
    }

For each page and viewport, the page is opened with Playwright, checked, and saved as
`<out>/<name>-<viewport>.png`. The checks are deliberately few and objective, so they
can fail a PR without arguing about taste:

- the page responds with a non-error status
- the `expect` text, if given, is visible
- no uncaught page errors and no console errors
- no failed requests (4xx/5xx) for the page's own assets and API calls
- nothing scrolls sideways at phone width
- every image has alt text
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

VIEWPORTS = {
    "desktop": {"width": 1280, "height": 800},
    "mobile": {"width": 360, "height": 780},
}

DEFAULT_PAGES = Path("docs/manual/pages.json")
DEFAULT_OUT = Path("docs/manual/screenshots")


@dataclass
class Shot:
    page: str
    viewport: str
    path: str
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def load_pages(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    pages = data["pages"] if isinstance(data, dict) else data
    for p in pages:
        if not p.get("name") or not p.get("path"):
            raise ValueError(f"every page needs a name and a path: {p}")
    return pages


def _same_origin(url: str, base: str) -> bool:
    return urlparse(url).netloc == urlparse(base).netloc


def shoot(base_url: str, pages: list[dict], out: Path, viewports=VIEWPORTS) -> list[Shot]:
    from playwright.sync_api import sync_playwright

    out.mkdir(parents=True, exist_ok=True)
    shots: list[Shot] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            for page_spec in pages:
                for vp_name in page_spec.get("viewports", list(viewports)):
                    shots.append(_shoot_one(browser, base_url, page_spec, vp_name,
                                            viewports[vp_name], out))
        finally:
            browser.close()
    return shots


def _shoot_one(browser, base_url: str, spec: dict, vp_name: str, size: dict, out: Path) -> Shot:
    file = out / f"{spec['name']}-{vp_name}.png"
    shot = Shot(spec["name"], vp_name, str(file))
    context = browser.new_context(viewport=size, device_scale_factor=1)
    page = context.new_page()
    page.on("pageerror", lambda e: shot.problems.append(f"page error: {e}"))
    page.on("console", lambda m: m.type == "error"
            and shot.problems.append(f"console error: {m.text[:200]}"))
    page.on("response", lambda r: r.status >= 400 and _same_origin(r.url, base_url)
            and shot.problems.append(f"HTTP {r.status}: {r.url}"))
    try:
        url = urljoin(base_url.rstrip("/") + "/", spec["path"].lstrip("/"))
        response = page.goto(url, wait_until="networkidle", timeout=30_000)
        if response is None or response.status >= 400:
            status = response.status if response else "no response"
            shot.problems.append(f"page returned {status}")
        expect = spec.get("expect")
        if expect and not page.get_by_text(expect).first.is_visible():
            shot.problems.append(f"expected text not visible: {expect!r}")
        if vp_name == "mobile":
            overflow = page.evaluate(
                "document.documentElement.scrollWidth - window.innerWidth"
            )
            if overflow > 1:
                shot.problems.append(f"scrolls sideways by {overflow}px at {size['width']}px")
        missing_alt = page.evaluate(
            "[...document.images].filter(i => !i.hasAttribute('alt')).length"
        )
        if missing_alt:
            shot.warnings.append(f"{missing_alt} image(s) without alt text")
        page.screenshot(path=str(file), full_page=True)
    except Exception as e:  # a page that can't load is a finding, not a crash
        shot.problems.append(f"could not load: {e}".splitlines()[0][:300])
    finally:
        context.close()
    return shot


def report(shots: list[Shot]) -> str:
    lines = ["| Page | Viewport | Result |", "|---|---|---|"]
    for s in shots:
        if s.problems:
            result = "✗ " + "; ".join(s.problems)
        elif s.warnings:
            result = "! " + "; ".join(s.warnings)
        else:
            result = "✓"
        lines.append(f"| {s.page} | {s.viewport} | {result} |")
    return "\n".join(lines)
