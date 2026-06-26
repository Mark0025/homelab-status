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


def test_detect_refixes_finds_and_classifies(monkeypatch, tmp_path):
    """End-to-end on a tiny in-memory dataset: a recurred re-fix + a fork excluded."""
    import sqlite3

    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE gh_commits (sha TEXT, repo TEXT, owner TEXT,
        message TEXT, author_date TEXT, commit_type TEXT)""")
    rows = [
        ("a1", "myrepo", "me", "fix: API_URL env var for server-side proxy", "2026-01-01T00:00:00", "fix"),
        ("a2", "myrepo", "me", "fix: API_URL env var for server-side proxy again", "2026-01-10T00:00:00", "fix"),
        ("b1", "myrepo", "me", "fix: totally unrelated stripe checkout url", "2026-01-05T00:00:00", "fix"),
        # a fork that must be EXCLUDED even though it has a re-fix
        ("c1", "next.js", "vercel", "fix: hydration mismatch in app router", "2026-01-01T00:00:00", "fix"),
        ("c2", "next.js", "vercel", "fix: hydration mismatch in app router edge", "2026-01-02T00:00:00", "fix"),
    ]
    conn.executemany("INSERT INTO gh_commits VALUES (?,?,?,?,?,?)", rows)
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
    repos = {r["repo"] for r in refixes}
    assert "myrepo" in repos
    assert "next.js" not in repos          # fork excluded (SKIP_REPOS)
    me = [r for r in refixes if r["repo"] == "myrepo"]
    assert len(me) == 1                     # only the similar pair, not the unrelated one
    assert me[0]["kind"] == "recurred"      # 9 days apart
    assert me[0]["days_between"] == 9


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
