"""Issue ingestion (#13 ecosystem learning) — the PROBLEM side of the arc.
GitHub's /issues returns PRs too; we must store only real issues."""

import contextlib
import sqlite3

import pytest

from homelab_status import timeline as tl


def _fake_conn(db):
    @contextlib.contextmanager
    def cm():
        c = sqlite3.connect(db); c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()          # mirror db.py:_conn() auto-commit on success
        finally:
            c.close()
    return cm


def test_save_issues_stores_shape(monkeypatch, tmp_path):
    db = tmp_path / "i.db"
    c = sqlite3.connect(db)
    c.execute("""CREATE TABLE gh_issues (id INTEGER PRIMARY KEY AUTOINCREMENT,
        number INTEGER, repo TEXT, owner TEXT, title TEXT, body TEXT, state TEXT,
        labels TEXT, author TEXT, comments INTEGER, created_at TEXT, closed_at TEXT,
        closed_by_pr INTEGER, fetched_at TEXT, UNIQUE(repo, owner, number))""")
    c.commit(); c.close()
    monkeypatch.setattr(tl, "_conn", _fake_conn(db))

    issues = [{
        "number": 7, "title": "thing broke", "body": "details", "state": "closed",
        "labels": [{"name": "bug"}], "user": {"login": "me"}, "comments": 2,
        "created_at": "2026-01-01T00:00:00Z", "closed_at": "2026-01-02T00:00:00Z",
    }]
    n = tl._save_issues(issues, "me", "myrepo")
    assert n == 1
    with _fake_conn(db)() as conn:
        row = conn.execute("SELECT * FROM gh_issues").fetchone()
    assert row["title"] == "thing broke"
    assert row["state"] == "closed"
    assert "bug" in row["labels"]


@pytest.mark.asyncio
async def test_fetch_issues_filters_out_prs(monkeypatch):
    """GitHub /issues includes PRs (they carry a 'pull_request' key) — drop them."""
    payload = [
        {"number": 1, "title": "real issue"},                       # keep
        {"number": 2, "title": "a PR", "pull_request": {"url": "x"}},  # drop
    ]

    class FakeResp:
        status_code = 200
        def json(self): return payload

    class FakeClient:
        async def get(self, *a, **k): return FakeResp()

    monkeypatch.setattr(tl, "_github_headers", lambda: {})
    out = await tl.fetch_issues_for_repo(FakeClient(), "me", "r")
    nums = [i["number"] for i in out]
    assert 1 in nums and 2 not in nums      # PR filtered out


@pytest.mark.asyncio
async def test_refresh_issues_aborts_without_token(monkeypatch):
    monkeypatch.delenv("GITHUB_PERSONAL_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    from homelab_status import git_history as g
    monkeypatch.setattr(g, "_token_from_gh_cli", lambda: "")
    result = await tl.refresh_issues()
    assert result["status"] == "error"
    assert result["issues_saved"] == 0
