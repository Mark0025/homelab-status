"""Issue #25: the dashboard moved from a _HTML string into templates/ + static/.
These tests guard that the extraction stays lossless and the static assets serve."""

from fastapi.testclient import TestClient

from homelab_status.web import api

client = TestClient(api)


def test_dashboard_serves_200_with_known_anchors():
    r = client.get("/")
    assert r.status_code == 200
    html = r.text
    # links to the extracted assets
    assert "/static/dashboard.css" in html
    assert "/static/dashboard.js" in html
    # the page chrome + all 7 tab labels are present
    assert "<title>Homelab Status</title>" in html
    for tab in ["Services", "API Routes", "Git History", "Timeline",
                "Dev Intelligence", "Plans", "Journey"]:
        assert tab in html, f"missing tab label: {tab}"


def test_static_assets_serve():
    assert client.get("/static/dashboard.css").status_code == 200
    assert client.get("/static/dashboard.js").status_code == 200


def test_no_inline_style_or_script_left_in_template():
    """The whole point of #25: chrome CSS/JS must live in files, not inline."""
    html = client.get("/").text
    # the page-chrome <style>…</style> block must be gone (moved to dashboard.css)
    assert "<style>" not in html
    # the big inline <script>…</script> app block must be gone (moved to dashboard.js);
    # only the external <script src=…> tags remain
    assert "<script>" not in html
