"""#42: LLM repo analysis — synthesize purpose+why from REAL code for thin-README
repos. LLM output is SYNTHESIS (source='llm'), grounded in code evidence."""

from homelab_status import repo_llm


def test_parse_llm_json_extracts_from_prose():
    raw = 'Sure!\n{"purpose": "A sales call API", "why": "routes Pete calls"}\nHope it helps'
    p, w = repo_llm._parse_llm_json(raw)
    assert p == "A sales call API"
    assert w == "routes Pete calls"


def test_parse_llm_json_fallback_to_sentences():
    p, w = repo_llm._parse_llm_json("This is a FastAPI webhook service. It exists for Twilio.")
    assert "FastAPI webhook service" in p


def test_analyze_all_resumable(monkeypatch, tmp_path):
    """The runner only analyzes repos WITHOUT analysis yet (resumable/chips through)."""
    import sqlite3, contextlib
    db = tmp_path / "t.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE gh_repos (owner TEXT, name TEXT, pushed_at TEXT)")
    c.execute("CREATE TABLE repo_llm_analysis (repo TEXT PRIMARY KEY, owner TEXT)")
    c.executemany("INSERT INTO gh_repos VALUES (?,?,?)",
                  [("Mark0025", "a", "x"), ("Mark0025", "b", "x"), ("Mark0025", "c", "x")])
    c.execute("INSERT INTO repo_llm_analysis VALUES ('a','Mark0025')")  # already done
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
    async def fake_analyze(owner, repo):
        analyzed.append(repo)
        return {"repo": repo, "purpose": "x"}
    monkeypatch.setattr(repo_llm, "analyze_repo", fake_analyze)

    import asyncio
    res = asyncio.run(repo_llm.analyze_all())
    # 'a' already analyzed -> only b, c get processed
    assert set(analyzed) == {"b", "c"}
    assert res["analyzed"] == 2
