"""#13: plan_reality measures a plan against its execution — 'working vs not'.
The deeper question than grade_doc's 'did it ship?' — did it ship WELL?"""

from homelab_status import mdops


def _setup(monkeypatch, signals, repo="myrepo"):
    monkeypatch.setattr(mdops, "get_doc", lambda i: {
        "title": "My Plan", "git_remotes": "github.com/Mark0025/%s" % repo, "project_remote": ""})
    monkeypatch.setattr(mdops, "_extract_github_repo", lambda *a: "Mark0025/%s" % repo)
    monkeypatch.setattr(mdops, "_repo_execution_signals", lambda r: signals)


def test_struggled_when_high_fix_ratio(monkeypatch):
    _setup(monkeypatch, {"feat": 40, "fix": 60, "prs": 10, "issues": 100, "open_issues": 50})
    r = mdops.plan_reality(1)
    assert r["verdict"] == "struggled"
    assert r["fix_ratio"] >= 0.5


def test_working_when_mostly_features(monkeypatch):
    _setup(monkeypatch, {"feat": 90, "fix": 10, "prs": 20, "issues": 50, "open_issues": 5})
    r = mdops.plan_reality(1)
    assert r["verdict"] == "working"


def test_not_executed_when_no_commits(monkeypatch):
    _setup(monkeypatch, {"feat": 0, "fix": 0, "prs": 0, "issues": 0, "open_issues": 0})
    r = mdops.plan_reality(1)
    assert r["verdict"] == "not-executed"


def test_unlinked_when_no_repo(monkeypatch):
    monkeypatch.setattr(mdops, "get_doc", lambda i: {"title": "X", "git_remotes": "", "project_remote": ""})
    monkeypatch.setattr(mdops, "_extract_github_repo", lambda *a: None)
    r = mdops.plan_reality(1)
    assert r["verdict"] == "unlinked"
