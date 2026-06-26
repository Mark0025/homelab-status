"""Issue #23: the dashboard must surface data freshness so it isn't confidently
wrong. The API exposes the freshness fields; the page wires a banner to them."""

from fastapi.testclient import TestClient

from homelab_status.web import api

client = TestClient(api)


def test_git_stats_exposes_freshness_fields():
    """The freshness signal the banner reads must exist in the API contract."""
    s = client.get("/api/git/stats").json()
    assert "last_fetched" in s          # when did we last sync GitHub
    assert "cache_fresh" in s           # is the cache within TTL
    assert "commits_last_7d" in s       # the 'idle vs broken' heuristic
    assert "total_commits" in s


def test_dashboard_has_stale_banner_element_and_logic():
    html = client.get("/").text
    assert 'id="stale-banner"' in html
    js = client.get("/static/dashboard.js").text
    assert "updateStaleBanner" in js
    # the three staleness conditions the banner distinguishes
    assert "Never synced" in js
    assert "0 commits ingested" in js
    assert "last 7 days" in js
    css = client.get("/static/dashboard.css").text
    assert ".stale-banner" in css
    assert ".stale-banner.broken" in css
