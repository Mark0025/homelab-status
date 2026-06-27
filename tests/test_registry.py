"""#13 keystone: the capability registry — machine-readable record an AGENT
routes on. Plus the README-purpose fix (was scraping HTML)."""

from homelab_status import project_intel as pi


def test_classify_deps_labels_ecosystem_and_purpose():
    out = pi._classify_deps(["fastapi", "langchain", "twilio", "weird-lib"], "python")
    by = {d["name"]: d for d in out}
    assert by["fastapi"]["ecosystem"] == "python"
    assert by["fastapi"]["does"] == "HTTP API framework"
    assert by["langchain"]["does"] == "LLM orchestration"
    assert by["weird-lib"]["does"] == ""        # unknown -> empty, not a guess


def test_clean_readme_prose_strips_html_and_badges():
    raw = '<picture><source srcset="x"></picture>\n[![badge](u)](l)\n![logo](img.png)\nfabric is a framework for X.'
    cleaned = pi._clean_readme_prose(raw)
    assert "<picture" not in cleaned
    assert "badge" not in cleaned and "img.png" not in cleaned
    assert "fabric is a framework for X." in cleaned


def test_extract_readme_purpose_is_prose_not_html():
    readme = '<div align="center">\n<img src="logo.png">\n</div>\n\nMyApp does cross-repo analysis.'
    purpose, _ = pi._extract_readme_sections(readme)
    assert "<div" not in purpose and "logo.png" not in purpose
    assert "cross-repo analysis" in purpose
