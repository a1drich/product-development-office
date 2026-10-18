import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from office import shoot

pytest.importorskip("playwright")

GOOD = """<!doctype html><html><head><meta name="viewport" content="width=device-width">
<title>Home</title></head><body><h1>Notes</h1><img src="data:," alt="logo"></body></html>"""

WIDE = """<!doctype html><html><head><meta name="viewport" content="width=device-width">
<title>Wide</title></head><body><div style="width:900px">too wide</div><img src="data:,">
<script>console.error("boom")</script></body></html>"""


@pytest.fixture
def site(tmp_path):
    (tmp_path / "index.html").write_text(GOOD)
    (tmp_path / "wide.html").write_text(WIDE)

    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=str(tmp_path)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_shoot_captures_and_checks(site, tmp_path):
    pages = [
        {"name": "home", "path": "/", "expect": "Notes"},
        {"name": "wide", "path": "/wide.html", "viewports": ["mobile"]},
        {"name": "missing", "path": "/nope.html", "viewports": ["desktop"]},
    ]
    out = tmp_path / "shots"
    shots = {(s.page, s.viewport): s for s in shoot.shoot(site, pages, out)}

    home = shots[("home", "desktop")]
    assert home.problems == [] and (out / "home-desktop.png").exists()
    assert (out / "home-mobile.png").exists()

    wide = shots[("wide", "mobile")]
    assert any("sideways" in p for p in wide.problems)
    assert any("console error" in p for p in wide.problems)
    assert any("alt text" in w for w in wide.warnings)

    assert any("404" in p for p in shots[("missing", "desktop")].problems)
    assert "✗" in shoot.report(list(shots.values()))


def test_load_pages_validates(tmp_path):
    f = tmp_path / "pages.json"
    f.write_text(json.dumps({"pages": [{"name": "home", "path": "/"}]}))
    assert shoot.load_pages(f)[0]["name"] == "home"
    f.write_text(json.dumps({"pages": [{"name": "home"}]}))
    with pytest.raises(ValueError):
        shoot.load_pages(f)
