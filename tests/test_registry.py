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


def test_business_domain_name_first_then_readme():
    # name = high confidence
    assert pi.business_domain("pete-db")["domain"] == "Pete (sales job)"
    assert pi.business_domain("pete-db")["confidence"] == "high"
    assert pi.business_domain("app.Aireinvestor")["domain"].startswith("aireinvestor")
    # README rescues a name that says nothing
    r = pi.business_domain("CALL-CENTER", "Sales call center for Pete intercom")
    assert r["domain"] == "Pete (sales job)"
    assert r["by"] == "readme"
    # honest unknown — never a forced guess
    u = pi.business_domain("DOG-AGE-CALC", "A calculator for dog age")
    assert u["domain"] == "custom / unknown"
    assert u["confidence"] == "low"
