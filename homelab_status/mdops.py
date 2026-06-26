"""
Plans & Docs — direct SQLite queries against the local MDOPS database.

Cross-references .md files with git history and GitHub PRs to grade
whether a plan actually shipped and what it produced.

No AI. Pure data comparison: md content → git commits → PRs → grade.
"""

from __future__ import annotations

import os
import re
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

MDOPS_DB = Path(os.environ.get("MDOPS_DB_PATH", "/Users/markcarpenter/00Myhomelab/MDDPY-MAC-GLOBAL/data-mac/mdops-mac.db"))
GITHUB_OWNER = "Mark0025"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(MDOPS_DB))
    conn.row_factory = sqlite3.Row
    return conn


# ── Search ────────────────────────────────────────────────────────────────────

def search_docs(q: str, limit: int = 50, git_only: bool = False) -> list[dict]:
    """Full-text search across all indexed .md files."""
    with _conn() as conn:
        if git_only:
            rows = conn.execute("""
                SELECT d.id, d.title, d.filename, d.full_path, d.word_count,
                       d.git_root, d.git_remotes, d.file_updated_at,
                       p.name as project, p.git_remote as project_remote
                FROM documents d
                LEFT JOIN projects p ON d.project_id = p.id
                WHERE (d.title LIKE ? OR d.filename LIKE ?)
                  AND d.git_root IS NOT NULL AND d.git_root != ''
                ORDER BY d.file_updated_at DESC NULLS LAST
                LIMIT ?
            """, (f"%{q}%", f"%{q}%", limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT d.id, d.title, d.filename, d.full_path, d.word_count,
                       d.git_root, d.git_remotes, d.file_updated_at,
                       p.name as project, p.git_remote as project_remote
                FROM documents d
                LEFT JOIN projects p ON d.project_id = p.id
                WHERE d.title LIKE ? OR d.filename LIKE ?
                ORDER BY d.file_updated_at DESC NULLS LAST
                LIMIT ?
            """, (f"%{q}%", f"%{q}%", limit)).fetchall()
    return [dict(r) for r in rows]


def list_projects(limit: int = 100) -> list[dict]:
    """List all projects that have .md files indexed."""
    with _conn() as conn:
        rows = conn.execute("""
            SELECT p.id, p.name, p.path, p.is_git_repo, p.git_remote,
                   p.git_branch, p.markdown_count, p.has_api, p.has_docker_compose,
                   p.last_modified, p.completion_state,
                   COUNT(d.id) as doc_count
            FROM projects p
            LEFT JOIN documents d ON d.project_id = p.id
            WHERE p.markdown_count > 0
            GROUP BY p.id
            ORDER BY p.last_modified DESC NULLS LAST
            LIMIT ?
        """, (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_doc(doc_id: int) -> dict | None:
    """Get a single document with full content."""
    with _conn() as conn:
        row = conn.execute("""
            SELECT d.*, p.name as project, p.git_remote as project_remote,
                   p.has_api, p.has_docker_compose, p.completion_state
            FROM documents d
            LEFT JOIN projects p ON d.project_id = p.id
            WHERE d.id = ?
        """, (doc_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    # Read actual file content
    path = Path(result.get("full_path", ""))
    if path.exists():
        try:
            result["content"] = path.read_text(errors="replace")[:8000]
        except Exception:
            result["content"] = None
    else:
        result["content"] = None
    return result


# ── Git cross-reference ───────────────────────────────────────────────────────

def _git_log(repo_path: str, file_path: str | None = None, limit: int = 20) -> list[dict]:
    """Run git log in a repo, optionally filtered to a specific file."""
    cmd = [
        "git", "-C", repo_path, "log",
        f"--max-count={limit}",
        "--pretty=format:%H|%as|%s|%an|%ae",
        "--no-merges",
    ]
    if file_path:
        cmd += ["--follow", "--", file_path]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=10).decode()
    except Exception:
        return []
    commits = []
    for line in out.strip().splitlines():
        parts = line.split("|", 4)
        if len(parts) == 5:
            sha, date, subject, author, email = parts
            commits.append({
                "sha": sha[:12],
                "sha_full": sha,
                "date": date,
                "subject": subject,
                "author": author,
                "is_bot": "bot" in email.lower() or "noreply" in email.lower(),
                "pr_number": _extract_pr_number(subject),
            })
    return commits


def _extract_pr_number(subject: str) -> int | None:
    """Extract PR number from commit subject like '(#42)' or 'Merge pull request #42'."""
    m = re.search(r'#(\d+)', subject)
    return int(m.group(1)) if m else None


def _extract_github_repo(git_remotes: str | None, project_remote: str | None) -> str | None:
    """Parse 'Mark0025/repo-name' from a remote URL."""
    for remote in [git_remotes, project_remote]:
        if not remote:
            continue
        m = re.search(r'github\.com[:/]([^/]+/[^/.]+)', remote)
        if m:
            return m.group(1)
    return None


# ── Grading ───────────────────────────────────────────────────────────────────

# Keywords that suggest a doc is a plan/spec (not just notes)
_PLAN_SIGNALS = [
    "plan", "spec", "design", "proposal", "roadmap", "todo", "strategy",
    "architecture", "implement", "build", "create", "add", "integrate",
    "telos", "goal", "objective", "requirement",
]

_SHIPPED_SIGNALS = [
    "feat:", "fix:", "add ", "implement", "complete", "done", "working",
    "deploy", "ship", "release", "finish",
]


def grade_doc(doc_id: int) -> dict:
    """
    Grade a plan doc against production data.

    Score breakdown (all from data, no AI):
      - has_git_history    (0/1)  — file was ever committed
      - commit_count       int    — how many commits touch this file
      - has_pr             (0/1)  — at least one PR references this file's repo
      - pr_count           int    — PRs in the same repo since file_updated_at
      - is_plan_doc        (0/1)  — filename/title contains plan signals
      - shipped_keywords   int    — commit subjects contain shipped signals
      - file_exists        (0/1)  — file still exists on disk
      - grade              A/B/C/D/F
    """
    doc = get_doc(doc_id)
    if not doc:
        return {"error": "doc not found"}

    path = doc.get("full_path", "")
    git_root = doc.get("git_root") or ""
    git_remotes = doc.get("git_remotes") or ""
    project_remote = doc.get("project_remote") or ""

    file_exists = Path(path).exists()
    is_plan_doc = any(s in (doc.get("filename") or "").lower() or
                      s in (doc.get("title") or "").lower()
                      for s in _PLAN_SIGNALS)

    # Git history for this specific file
    commits = []
    if git_root:
        commits = _git_log(git_root, path, limit=30)

    commit_count = len(commits)
    has_git_history = commit_count > 0

    shipped_keywords = sum(
        1 for c in commits
        if any(s in c["subject"].lower() for s in _SHIPPED_SIGNALS)
    )

    pr_numbers = [c["pr_number"] for c in commits if c["pr_number"]]
    has_pr = len(pr_numbers) > 0

    # Repo-level PR count from our local PR DB (from homelab-status itself)
    pr_count = _count_prs_for_repo(git_remotes, project_remote)

    # Grade: purely mechanical
    score = (
        (2 if has_git_history else 0) +
        (min(commit_count, 3)) +          # up to 3 pts for commits
        (3 if has_pr else 0) +
        (min(pr_count // 5, 3)) +         # up to 3 pts for repo PRs
        (1 if shipped_keywords > 0 else 0) +
        (1 if file_exists else 0)
    )

    if score >= 10:
        grade = "A"
    elif score >= 7:
        grade = "B"
    elif score >= 4:
        grade = "C"
    elif score >= 2:
        grade = "D"
    else:
        grade = "F"

    github_repo = _extract_github_repo(git_remotes, project_remote)

    return {
        "doc_id": doc_id,
        "title": doc.get("title"),
        "filename": doc.get("filename"),
        "full_path": path,
        "file_exists": file_exists,
        "is_plan_doc": is_plan_doc,
        "git_root": git_root,
        "github_repo": github_repo,
        "has_git_history": has_git_history,
        "commit_count": commit_count,
        "has_pr": has_pr,
        "pr_numbers": pr_numbers[:10],
        "pr_count": pr_count,
        "shipped_keywords": shipped_keywords,
        "score": score,
        "grade": grade,
        "recent_commits": commits[:10],
        "grade_breakdown": {
            "has_git_history": 2 if has_git_history else 0,
            "commit_depth": min(commit_count, 3),
            "has_pr": 3 if has_pr else 0,
            "repo_pr_activity": min(pr_count // 5, 3),
            "shipped_language": 1 if shipped_keywords > 0 else 0,
            "file_exists": 1 if file_exists else 0,
        },
    }


def _count_prs_for_repo(git_remotes: str, project_remote: str) -> int:
    """Count merged PRs for a repo from the local homelab-status PR DB."""
    from .db import _conn as hs_conn
    github_repo = _extract_github_repo(git_remotes, project_remote)
    if not github_repo:
        return 0
    _, repo = github_repo.split("/", 1) if "/" in github_repo else ("", github_repo)
    try:
        with hs_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM gh_pull_requests WHERE repo=? AND merged_at IS NOT NULL",
                (repo,)
            ).fetchone()
            return row[0] if row else 0
    except Exception:
        return 0


def _repo_execution_signals(repo: str) -> dict:
    """Pull execution signals for a repo from status.db (commits/PRs/issues).
    The DEEPER question than grade_doc's 'did it ship?': 'did it ship WELL?'."""
    from .db import _conn as hs_conn
    try:
        with hs_conn() as conn:
            feat = conn.execute("SELECT COUNT(*) FROM gh_commits WHERE repo=? AND commit_type='feat'", (repo,)).fetchone()[0]
            fix = conn.execute("SELECT COUNT(*) FROM gh_commits WHERE repo=? AND commit_type='fix'", (repo,)).fetchone()[0]
            prs = conn.execute("SELECT COUNT(*) FROM gh_pull_requests WHERE repo=?", (repo,)).fetchone()[0]
            has_issues = conn.execute("SELECT name FROM sqlite_master WHERE name='gh_issues'").fetchone()
            issues = open_issues = 0
            if has_issues:
                issues = conn.execute("SELECT COUNT(*) FROM gh_issues WHERE repo=?", (repo,)).fetchone()[0]
                open_issues = conn.execute("SELECT COUNT(*) FROM gh_issues WHERE repo=? AND state='open'", (repo,)).fetchone()[0]
    except Exception:
        feat = fix = prs = issues = open_issues = 0
    return {"feat": feat, "fix": fix, "prs": prs, "issues": issues, "open_issues": open_issues}


def plan_reality(doc_id: int) -> dict:
    """#13 — measure a plan against its execution: 'what was WORKING vs NOT'.

    grade_doc answers 'did stuff happen near this plan?' (activity). This answers
    the harder question — did the plan's intent get achieved, or did it struggle?
    WORKING signals: feat commits, low fix-ratio, few open issues.
    STRUGGLED signals: high fix-ratio, many open issues (the gap between a plan
    that says 'Complete ✅' and an execution that kept breaking).
    """
    doc = get_doc(doc_id)
    if not doc:
        return {"error": "doc not found"}

    github = _extract_github_repo(doc.get("git_remotes") or "", doc.get("project_remote") or "")
    repo = github.split("/", 1)[1] if github and "/" in github else (github or "")
    if not repo:
        return {"doc_id": doc_id, "title": doc.get("title"), "verdict": "unlinked",
                "reason": "plan not linked to a GitHub repo (no git_remotes match)"}

    sig = _repo_execution_signals(repo)
    total = sig["feat"] + sig["fix"]
    fix_ratio = round(sig["fix"] / total, 2) if total else 0.0
    open_ratio = round(sig["open_issues"] / sig["issues"], 2) if sig["issues"] else 0.0

    # deterministic verdict — no AI, all from data
    if total == 0:
        verdict, reason = "not-executed", "plan exists but no feat/fix commits in the repo"
    elif fix_ratio >= 0.5 or open_ratio >= 0.4:
        verdict = "struggled"
        reason = f"high fix-ratio ({int(fix_ratio*100)}%) / open-issue-ratio ({int(open_ratio*100)}%) — execution diverged from the plan"
    elif fix_ratio <= 0.3 and open_ratio <= 0.2:
        verdict, reason = "working", f"mostly feature work (fix-ratio {int(fix_ratio*100)}%), issues resolved"
    else:
        verdict, reason = "mixed", f"fix-ratio {int(fix_ratio*100)}%, open-issue-ratio {int(open_ratio*100)}%"

    return {
        "doc_id": doc_id, "title": doc.get("title"), "repo": repo,
        "verdict": verdict, "reason": reason,
        "fix_ratio": fix_ratio, "open_issue_ratio": open_ratio,
        "signals": sig,
    }


# ── Repo-linked docs (for Dev Intelligence cards) ────────────────────────────

def docs_for_repo(repo_name: str, owner: str = "Mark0025") -> list[dict]:
    """
    Return all .md docs indexed in MDOPS whose git remote matches this repo.
    Each doc gets a lightweight grade (commit count + file exists) — no subprocess
    per-doc since this is called for every repo card render.
    """
    with _conn() as conn:
        rows = conn.execute("""
            SELECT d.id, d.title, d.filename, d.full_path, d.relative_path,
                   d.word_count, d.git_root, d.git_remotes, d.file_updated_at,
                   p.name as project
            FROM documents d
            LEFT JOIN projects p ON d.project_id = p.id
            WHERE d.git_remotes LIKE ?
            ORDER BY d.file_updated_at DESC NULLS LAST
        """, (f"%{repo_name}%",)).fetchall()

    docs = []
    for r in rows:
        d = dict(r)
        path = Path(d.get("full_path", ""))
        d["file_exists"] = path.exists()
        # Quick plan signal check — no git subprocess here for speed
        name_lower = (d.get("filename") or "").lower()
        title_lower = (d.get("title") or "").lower()
        d["is_plan"] = any(s in name_lower or s in title_lower for s in _PLAN_SIGNALS)
        docs.append(d)
    return docs


# ── Stats ─────────────────────────────────────────────────────────────────────

def doc_stats() -> dict:
    """Summary stats for the Plans tab header."""
    with _conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        with_git = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE git_root IS NOT NULL AND git_root != ''"
        ).fetchone()[0]
        projects = conn.execute("SELECT COUNT(*) FROM projects WHERE markdown_count > 0").fetchone()[0]
        plan_docs = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE "
            "LOWER(filename) LIKE '%plan%' OR LOWER(filename) LIKE '%spec%' OR "
            "LOWER(filename) LIKE '%telos%' OR LOWER(filename) LIKE '%design%' OR "
            "LOWER(title) LIKE '%plan%' OR LOWER(title) LIKE '%roadmap%'"
        ).fetchone()[0]
    return {
        "total_docs": total,
        "with_git": with_git,
        "projects": projects,
        "plan_docs": plan_docs,
    }
