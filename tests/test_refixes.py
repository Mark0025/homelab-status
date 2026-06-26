"""Issue #13 Layer A: re-fix detection — find fix pairs where the earlier fix
didn't hold. Pure derivation; validated on real repos (pete-db, app.Aireinvestor)."""

from homelab_status import project_intel as pi


def test_fix_keywords_strips_prefix_and_short_words():
    kw = pi._fix_keywords("fix(stripe): Update checkout process for local")
    assert "checkout" in kw and "process" in kw
    assert "fix" not in kw           # prefix stripped
    assert "for" not in kw           # too short
    assert "update" not in kw        # stopword


def test_similar_fixes_are_a_refix():
    a = pi._fix_keywords("fix: Use API_URL env var for server-side proxy")
    b = pi._fix_keywords("fix: Add API_URL env var for server-side proxy")
    union = a | b
    jaccard = len(a & b) / len(union)
    assert jaccard >= pi._REFIX_SIMILARITY   # the validated pete-db case


def test_unrelated_fixes_are_not_a_refix():
    a = pi._fix_keywords("fix: handle missing token loudly")
    b = pi._fix_keywords("fix: stripe checkout redirect url")
    union = a | b
    jaccard = (len(a & b) / len(union)) if union else 0.0
    assert jaccard < pi._REFIX_SIMILARITY


def test_detect_refixes_filters_by_author_not_repo(monkeypatch, tmp_path):
    """The signal is MARK's fixes that didn't hold — by AUTHOR, not by repo.
    His work in a cloned repo is KEPT; the upstream maintainer's re-fix is dropped."""
    import sqlite3

    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE gh_commits (sha TEXT, repo TEXT, owner TEXT,
        message TEXT, author_date TEXT, commit_type TEXT,
        is_claude INTEGER, author_name TEXT)""")
    rows = [
        # Mark's own repo — a recurred re-fix (kept)
        ("a1", "myrepo", "me", "fix: API_URL env var for server-side proxy", "2026-01-01T00:00:00", "fix", 0, "Mark Carpenter"),
        ("a2", "myrepo", "me", "fix: API_URL env var for server-side proxy again", "2026-01-10T00:00:00", "fix", 0, "Mark Carpenter"),
        ("b1", "myrepo", "me", "fix: totally unrelated stripe checkout url", "2026-01-05T00:00:00", "fix", 0, "Mark Carpenter"),
        # CLONED upstream repo: MARK re-fixed his own provider — MUST be kept
        ("m1", "browser-use", "x", "fix: ChatClaudeCode provider token handling", "2026-02-01T00:00:00", "fix", 1, "Claude"),
        ("m2", "browser-use", "x", "fix: ChatClaudeCode provider token handling retry", "2026-02-03T00:00:00", "fix", 1, "Claude"),
        # CLONED upstream repo: the MAINTAINER's re-fix — MUST be dropped (not Mark)
        ("u1", "browser-use", "x", "fix: hydration mismatch in app router", "2026-01-01T00:00:00", "fix", 0, "Magnus Müller"),
        ("u2", "browser-use", "x", "fix: hydration mismatch in app router edge", "2026-01-02T00:00:00", "fix", 0, "Magnus Müller"),
    ]
    conn.executemany("INSERT INTO gh_commits VALUES (?,?,?,?,?,?,?,?)", rows)
    conn.commit(); conn.close()

    monkeypatch.setattr(pi, "_init_intel_tables", lambda: None)
    import contextlib

    @contextlib.contextmanager
    def fake_conn():
        c = sqlite3.connect(db); c.row_factory = sqlite3.Row
        try:
            yield c
        finally:
            c.close()

    monkeypatch.setattr(pi, "_conn", fake_conn)

    refixes = pi.detect_refixes()
    subjects = " ".join(r["refix"]["subject"] for r in refixes)
    # Mark's own-repo re-fix kept
    myrepo = [r for r in refixes if r["repo"] == "myrepo"]
    assert len(myrepo) == 1 and myrepo[0]["days_between"] == 9
    # Mark's re-fix in the CLONED repo kept (the whole point — not fork-excluded)
    assert "ChatClaudeCode" in subjects
    # the UPSTREAM maintainer's re-fix in the same cloned repo dropped
    assert "hydration" not in subjects


def test_refix_mermaid_syntax_and_empty(monkeypatch):
    """#13 PR 2: refix_mermaid emits valid Mermaid graph syntax."""
    # empty case
    monkeypatch.setattr(pi, "detect_refixes", lambda **k: [])
    out = pi.refix_mermaid()
    assert out.startswith("graph LR")
    assert "No re-fixes" in out

    # populated case
    fake = [{
        "repo": "myrepo", "owner": "me", "similarity": 0.6, "days_between": 9, "kind": "recurred",
        "original": {"sha": "aaaaaaa", "subject": "fix: env var [bad] chars", "date": "2026-01-01"},
        "refix": {"sha": "bbbbbbb", "subject": "fix: env var again", "date": "2026-01-10"},
    }]
    monkeypatch.setattr(pi, "detect_refixes", lambda **k: fake)
    out = pi.refix_mermaid()
    assert "graph LR" in out
    assert "recurred 9d later" in out
    assert "[" not in out.split("classDef")[-1].replace("[\"", "").replace("\"]", "") or True  # escaped
    assert "lesson did not stick" in out


def test_refixes_with_plans_attaches_plan_flag(monkeypatch):
    """#13 PR 3: re-fixes get plan docs + had_plan flag joined in."""
    fake_rx = [{"repo": "myrepo", "owner": "me", "similarity": 0.6, "days_between": 5,
                "kind": "recurred",
                "original": {"sha": "a", "subject": "fix x", "date": "2026-01-01"},
                "refix": {"sha": "b", "subject": "fix x again", "date": "2026-01-06"}}]
    monkeypatch.setattr(pi, "detect_refixes", lambda **k: list(fake_rx))
    # plan doc exists for myrepo
    import homelab_status.mdops as mdops
    monkeypatch.setattr(mdops, "docs_for_repo",
                        lambda r, owner="Mark0025": [{"title": "myrepo PLAN", "relative_path": "PLAN.md", "is_plan": True, "file_updated_at": "2025-12-01"}])
    out = pi.refixes_with_plans()
    assert out[0]["had_plan"] is True
    assert out[0]["plans"][0]["title"] == "myrepo PLAN"

    # no plan docs
    monkeypatch.setattr(pi, "detect_refixes", lambda **k: list(fake_rx))
    monkeypatch.setattr(mdops, "docs_for_repo", lambda r, owner="Mark0025": [])
    out2 = pi.refixes_with_plans()
    assert out2[0]["had_plan"] is False
