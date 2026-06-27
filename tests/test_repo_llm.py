"""#42: LLM repo analysis — synthesize purpose+why from REAL code for thin-README
repos. LLM output is SYNTHESIS (source='llm'), grounded in code evidence."""

from homelab_status import repo_llm


def test_parse_llm_json_extracts_from_prose():
    raw = 'Sure!\n{"purpose": "A sales call API", "why": "routes Pete calls", "grade": "B", "maturity": "working"}\nHope it helps'
    p, w, g, m = repo_llm._parse_llm_json(raw)
    assert p == "A sales call API"
    assert w == "routes Pete calls"
    assert g == "B" and m == "working"


def test_parse_llm_json_fallback_to_sentences():
    p, w, g, m = repo_llm._parse_llm_json("This is a FastAPI webhook service. It exists for Twilio.")
    assert "FastAPI webhook service" in p


def test_analyze_all_skips_repos_done_this_lens_today(monkeypatch, tmp_path):
    """Daily-loop resumability: skip repos already analyzed under THIS lens TODAY."""
    import sqlite3, contextlib
    from datetime import datetime
    db = tmp_path / "t.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE gh_repos (owner TEXT, name TEXT, pushed_at TEXT)")
    c.execute("""CREATE TABLE repo_llm_analysis (id INTEGER PRIMARY KEY AUTOINCREMENT,
        repo TEXT, owner TEXT, lens TEXT, analyzed_at TEXT)""")
    c.executemany("INSERT INTO gh_repos VALUES (?,?,?)",
                  [("Mark0025", "a", "x"), ("Mark0025", "b", "x"), ("Mark0025", "c", "x")])
    # 'a' already done under baseline TODAY -> should be skipped
    c.execute("INSERT INTO repo_llm_analysis (repo, owner, lens, analyzed_at) VALUES ('a','Mark0025','baseline',?)",
              (datetime.now().isoformat(),))
    c.commit(); c.close()

    @contextlib.contextmanager
    def fake_conn():
        cc = sqlite3.connect(db); cc.row_factory = sqlite3.Row
        try:
            yield cc; cc.commit()
        finally:
            cc.close()
    monkeypatch.setattr(repo_llm, "_conn", fake_conn)
    monkeypatch.setattr(repo_llm, "_init_llm_table", lambda: None)

    analyzed = []
    async def fake_analyze(owner, repo, lens="baseline"):
        analyzed.append(repo)
        return {"repo": repo, "purpose": "x"}
    monkeypatch.setattr(repo_llm, "analyze_repo", fake_analyze)

    import asyncio
    res = asyncio.run(repo_llm.analyze_all(lens="baseline"))
    assert set(analyzed) == {"b", "c"}     # 'a' skipped (done this lens today)
    assert res["analyzed"] == 2


def test_append_only_snapshots_keep_history(monkeypatch, tmp_path):
    """#52 foundation: each analyze APPENDS a dated snapshot (never overwrites),
    so a timeline accumulates; get_llm_analysis returns the LATEST."""
    import asyncio, sqlite3, contextlib
    from homelab_status import repo_llm as r

    db = tmp_path / "a.db"
    @contextlib.contextmanager
    def fake_conn():
        c = sqlite3.connect(db); c.row_factory = sqlite3.Row
        try:
            yield c; c.commit()
        finally:
            c.close()
    monkeypatch.setattr(r, "_conn", fake_conn)
    monkeypatch.setattr(r, "init_db", lambda: None)
    r._init_llm_table()

    monkeypatch.setattr(r, "_ask_claude_http",
        lambda p: '{"purpose":"p","why":"w","grade":"B","maturity":"working"}')
    async def fake_audit(o, repo): return {"deps": [], "dep_source": "x", "routes": []}
    monkeypatch.setattr(r, "code_audit", fake_audit)
    async def fake_fetch(c, o, repo, p): return ""
    monkeypatch.setattr(r, "_fetch_file_content", fake_fetch)

    asyncio.run(r.analyze_repo("Mark0025", "demo", lens="baseline"))
    asyncio.run(r.analyze_repo("Mark0025", "demo", lens="efficiency"))
    hist = r.get_analysis_history("demo")
    assert len(hist) == 2                          # BOTH kept (append, not overwrite)
    assert {h["lens"] for h in hist} == {"baseline", "efficiency"}
    assert r.get_llm_analysis("demo") is not None  # latest exists


def test_migration_from_old_overwrite_schema(monkeypatch, tmp_path):
    """An OLD repo_llm_analysis (repo PRIMARY KEY, no id/lens) migrates without data loss."""
    import sqlite3, contextlib
    from homelab_status import repo_llm as r
    db = tmp_path / "old.db"
    c = sqlite3.connect(db)
    c.execute("""CREATE TABLE repo_llm_analysis (repo TEXT PRIMARY KEY, owner TEXT NOT NULL,
        llm_purpose TEXT, llm_why TEXT, source TEXT, model TEXT, evidence TEXT, analyzed_at TEXT NOT NULL)""")
    c.execute("INSERT INTO repo_llm_analysis VALUES ('old-repo','Mark0025','op','ow','llm','m','e','2026-01-01')")
    c.commit(); c.close()

    @contextlib.contextmanager
    def fake_conn():
        cc = sqlite3.connect(db); cc.row_factory = sqlite3.Row
        try:
            yield cc; cc.commit()
        finally:
            cc.close()
    monkeypatch.setattr(r, "_conn", fake_conn)
    monkeypatch.setattr(r, "init_db", lambda: None)
    r._init_llm_table()   # triggers migration

    a = r.get_llm_analysis("old-repo")
    assert a is not None and a["llm_purpose"] == "op"   # old row preserved
    assert a["lens"] == "baseline"                       # new column defaulted


def test_bootstrap_parses_report(monkeypatch, tmp_path):
    """Bootstrap loads REPO-ANALYSIS.md entries into the snapshot table."""
    import sqlite3, contextlib
    from homelab_status import repo_llm as r
    report = tmp_path / "rep.md"
    report.write_text(
        "# Repo Analysis\n> Generated 2026-06-27\n\n"
        "### myapp  `B` · working · 10 commits\n"
        "**What:** Does a thing.\n\n**Why:** Because reasons.\n\n"
        "### empty-one  `F` · empty · 1 commits\n"
        "**What:** Cannot be determined.\n\n**Why:** No evidence.\n")
    db = tmp_path / "b.db"
    @contextlib.contextmanager
    def fake_conn():
        c = sqlite3.connect(db); c.row_factory = sqlite3.Row
        try:
            yield c; c.commit()
        finally:
            c.close()
    monkeypatch.setattr(r, "_conn", fake_conn)
    monkeypatch.setattr(r, "init_db", lambda: None)
    res = r.bootstrap_from_report(str(report))
    assert res["imported"] == 2
    a = r.get_llm_analysis("myapp")
    assert a["grade"] == "B" and a["maturity"] == "working" and "Does a thing" in a["llm_purpose"]
