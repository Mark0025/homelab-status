"""
Git history service — pulls commit data from GitHub API across all repos/orgs,
caches in SQLite, serves stale-while-revalidate. Fast on every call.
"""

import asyncio
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from loguru import logger
from pydantic import BaseModel

from .db import _conn, init_db

# ── Config ─────────────────────────────────────────────────────────────────

def _token_from_gh_cli() -> str:
    try:
        result = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""

GITHUB_TOKEN = (
    os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
    or os.environ.get("GH_TOKEN")
    or _token_from_gh_cli()
)

GITHUB_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

# All GitHub identities to scan
GITHUB_OWNERS = ["Mark0025", "THE-AI-REAL-ESTATE-INVESTOR", "Local-House-Buyers"]

# Repos to SKIP (forks, tutorials, noise)
SKIP_REPOS = {
    # Tutorial / learning repos
    "crewAI", "Auto-GPT", "autogen", "awesome-chatgpt-prompts", "awesome-cursorrules",
    "crewAI-tools", "devops-directive-terraform-course", "crewai-groq-tutorial",
    "crewai-updated-tutorial-hierarchical", "CrewAI-Visualizer", "linux_cheats_cli",
    "FARM-STACK-LEARNING", "demo-repository", "learn-excelljs", "tictok-auto",
    "organize-git",
    # Large upstream forks — not Mark's code, just cloned for reference
    # Note: browser-use has 7 real commits by Mark (ChatClaudeCode provider) — kept
    "next.js", "uptime-kuma", "open-webui", "langflow",
    "opencode-dev", "terraform-provider-mongodbatlas", "nginx-proxy-manager",
    "AI_Agents_DB", "Flowise", "MemGPT", "quickstart-plaid",
    "superagent", "OPENAPI_Documentation",
}

CACHE_TTL_HOURS = 6   # refresh repo list every 6h
COMMIT_CACHE_HOURS = 2  # refresh individual repo commits every 2h


# ── Pydantic models ─────────────────────────────────────────────────────────

class CommitAuthor(BaseModel):
    name: str
    email: str
    date: str


class CommitStats(BaseModel):
    additions: int = 0
    deletions: int = 0
    files_changed: int = 0


class Commit(BaseModel):
    sha: str
    short_sha: str
    message: str
    subject: str          # first line of message
    body: str             # rest of message
    author: CommitAuthor
    stats: CommitStats
    repo: str
    owner: str
    url: str


class RepoSummary(BaseModel):
    name: str
    full_name: str
    owner: str
    description: str = ""
    language: str = ""
    private: bool = False
    pushed_at: str = ""
    html_url: str = ""
    commit_count: int = 0
    last_commit_at: str = ""
    last_commit_msg: str = ""


# ── DB schema ────────────────────────────────────────────────────────────────

def _init_git_tables() -> None:
    init_db()
    with _conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS gh_repos (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name    TEXT UNIQUE NOT NULL,
            owner        TEXT NOT NULL,
            name         TEXT NOT NULL,
            description  TEXT DEFAULT '',
            language     TEXT DEFAULT '',
            private      INTEGER DEFAULT 0,
            pushed_at    TEXT DEFAULT '',
            html_url     TEXT DEFAULT '',
            fetched_at   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS gh_commits (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            sha          TEXT NOT NULL,
            repo         TEXT NOT NULL,
            owner        TEXT NOT NULL,
            message      TEXT NOT NULL,
            author_name  TEXT NOT NULL,
            author_email TEXT NOT NULL,
            author_date  TEXT NOT NULL,
            additions    INTEGER DEFAULT 0,
            deletions    INTEGER DEFAULT 0,
            files_changed INTEGER DEFAULT 0,
            url          TEXT DEFAULT '',
            fetched_at   TEXT NOT NULL,
            UNIQUE(sha, repo)
        );

        CREATE TABLE IF NOT EXISTS gh_fetch_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            repo       TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            commit_count INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_gh_commits_repo  ON gh_commits(repo);
        CREATE INDEX IF NOT EXISTS idx_gh_commits_date  ON gh_commits(author_date);
        CREATE INDEX IF NOT EXISTS idx_gh_commits_sha   ON gh_commits(sha);
        CREATE INDEX IF NOT EXISTS idx_gh_repos_owner   ON gh_repos(owner);
        """)


def _repo_needs_refresh(full_name: str) -> bool:
    with _conn() as conn:
        row = conn.execute(
            "SELECT fetched_at FROM gh_fetch_log WHERE repo=? ORDER BY id DESC LIMIT 1",
            (full_name,),
        ).fetchone()
    if not row:
        return True
    fetched = datetime.fromisoformat(row["fetched_at"])
    return datetime.now() - fetched > timedelta(hours=COMMIT_CACHE_HOURS)


def _repos_need_refresh() -> bool:
    with _conn() as conn:
        row = conn.execute(
            "SELECT fetched_at FROM gh_repos ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row:
        return True
    fetched = datetime.fromisoformat(row["fetched_at"])
    return datetime.now() - fetched > timedelta(hours=CACHE_TTL_HOURS)


# ── GitHub API fetchers ───────────────────────────────────────────────────────

async def _gh_get(client: httpx.AsyncClient, url: str, params: dict | None = None) -> list | dict | None:
    try:
        resp = await client.get(url, headers=GITHUB_HEADERS, params=params, timeout=15.0)
        if resp.status_code == 200:
            return resp.json()
        logger.warning(f"GitHub API {url} → {resp.status_code}")
        return None
    except Exception as e:
        logger.warning(f"GitHub API error {url}: {e}")
        return None


async def _fetch_all_repos(client: httpx.AsyncClient) -> list[dict]:
    """Fetch repos from Mark0025 personal account + all orgs."""
    all_repos: list[dict] = []

    # Personal repos
    page = 1
    while True:
        data = await _gh_get(client, "https://api.github.com/user/repos",
                              params={"per_page": 100, "page": page, "type": "owner"})
        if not data:
            break
        all_repos.extend(data)
        if len(data) < 100:
            break
        page += 1

    # Org repos
    for org in GITHUB_OWNERS[1:]:  # skip Mark0025, already covered above
        page = 1
        while True:
            data = await _gh_get(client, f"https://api.github.com/orgs/{org}/repos",
                                  params={"per_page": 100, "page": page, "type": "all"})
            if not data:
                break
            all_repos.extend(data)
            if len(data) < 100:
                break
            page += 1

    return all_repos


async def _fetch_commits_for_repo(
    client: httpx.AsyncClient, owner: str, repo: str, since: str | None = None
) -> list[dict]:
    """Fetch all commits for a repo, paginating through all pages.
    If `since` is provided (ISO 8601), only fetch commits newer than that date.
    """
    all_commits: list[dict] = []
    page = 1
    params: dict = {"per_page": 100}
    if since:
        params["since"] = since

    while True:
        params["page"] = page
        data = await _gh_get(
            client,
            f"https://api.github.com/repos/{owner}/{repo}/commits",
            params=params,
        )
        if not data or not isinstance(data, list):
            break
        all_commits.extend(data)
        if len(data) < 100:
            break
        page += 1

    return all_commits


# ── Refresh logic (background, non-blocking) ─────────────────────────────────

_refresh_lock = asyncio.Lock()
_refresh_running = False


async def refresh_all(force: bool = False) -> dict:
    """Fetch all repos + recent commits. Safe to call from background task."""
    global _refresh_running
    if _refresh_running and not force:
        return {"status": "already_running"}

    async with _refresh_lock:
        _refresh_running = True
        try:
            return await _do_refresh(force)
        finally:
            _refresh_running = False


async def _do_refresh(force: bool = False) -> dict:
    _init_git_tables()
    ts = datetime.now().isoformat()
    stats = {"repos_found": 0, "repos_refreshed": 0, "commits_saved": 0}

    async with httpx.AsyncClient() as client:
        # ── Step 1: fetch/cache repo list ──────────────────────────────────
        if force or _repos_need_refresh():
            logger.info("Fetching repo list from GitHub...")
            raw_repos = await _fetch_all_repos(client)
            repos = [r for r in raw_repos if r["name"] not in SKIP_REPOS]
            stats["repos_found"] = len(repos)

            with _conn() as conn:
                conn.executemany(
                    """INSERT INTO gh_repos
                       (full_name, owner, name, description, language, private, pushed_at, html_url, fetched_at)
                       VALUES (?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(full_name) DO UPDATE SET
                         description=excluded.description, language=excluded.language,
                         pushed_at=excluded.pushed_at, fetched_at=excluded.fetched_at""",
                    [(
                        r["full_name"],
                        r["owner"]["login"],
                        r["name"],
                        r.get("description") or "",
                        r.get("language") or "",
                        int(r.get("private", False)),
                        r.get("pushed_at", ""),
                        r.get("html_url", ""),
                        ts,
                    ) for r in repos],
                )
            logger.info(f"Cached {len(repos)} repos")
        else:
            stats["repos_found"] = _count_cached_repos()

        # ── Step 2: fetch commits for repos needing refresh ───────────────
        with _conn() as conn:
            repo_rows = conn.execute(
                "SELECT full_name, owner, name FROM gh_repos ORDER BY pushed_at DESC"
            ).fetchall()

        sem = asyncio.Semaphore(8)  # don't hammer GitHub rate limits

        async def _refresh_repo(row: dict) -> int:
            full_name = row["full_name"]
            if not force and not _repo_needs_refresh(full_name):
                return 0
            async with sem:
                # Only fetch commits newer than what we already have
                since = _latest_commit_date(row["name"], row["owner"]) if not force else None
                commits = await _fetch_commits_for_repo(client, row["owner"], row["name"], since=since)
                if not commits:
                    _log_fetch(full_name, 0)
                    return 0
                saved = _save_commits(commits, row["owner"], row["name"])
                _log_fetch(full_name, saved)
                logger.debug(f"  {full_name}: {saved} new commits (since={since or 'beginning'})")
                return saved

        results = await asyncio.gather(*[_refresh_repo(dict(r)) for r in repo_rows])
        refreshed = sum(1 for r in results if r > 0)
        total_commits = sum(results)
        stats["repos_refreshed"] = refreshed
        stats["commits_saved"] = total_commits
        logger.info(f"Git refresh done: {refreshed} repos, {total_commits} commits")
        return stats


def _save_commits(raw: list[dict], owner: str, repo: str) -> int:
    ts = datetime.now().isoformat()
    rows = []
    for c in raw:
        commit = c.get("commit", {})
        author = commit.get("author") or {}
        stats = c.get("stats") or {}
        rows.append((
            c["sha"], repo, owner,
            commit.get("message", ""),
            author.get("name", ""),
            author.get("email", ""),
            author.get("date", ""),
            stats.get("additions", 0),
            stats.get("deletions", 0),
            stats.get("files", 0),
            c.get("html_url", ""),
            ts,
        ))
    with _conn() as conn:
        conn.executemany(
            """INSERT OR IGNORE INTO gh_commits
               (sha, repo, owner, message, author_name, author_email, author_date,
                additions, deletions, files_changed, url, fetched_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
    return len(rows)


def _latest_commit_date(repo: str, owner: str) -> str | None:
    """Return the most recent commit date for a repo (ISO 8601), or None if none cached."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT MAX(author_date) FROM gh_commits WHERE repo=? AND owner=?",
            (repo, owner),
        ).fetchone()
    return row[0] if row and row[0] else None


def _log_fetch(full_name: str, count: int) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO gh_fetch_log (repo, fetched_at, commit_count) VALUES (?,?,?)",
            (full_name, datetime.now().isoformat(), count),
        )


def _count_cached_repos() -> int:
    with _conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM gh_repos").fetchone()[0]


# ── Query functions (always fast — reads from cache) ─────────────────────────

def get_recent_commits(limit: int = 10000, repo: str | None = None, owner: str | None = None) -> list[dict]:
    """Return commits from cache. limit=0 means no limit. Default 10k covers all real repos."""
    _init_git_tables()
    query = "SELECT * FROM gh_commits"
    params: list = []
    clauses: list[str] = []
    if repo:
        # Exact match on repo name (repo filter is user-selected from dropdown, not a search)
        clauses.append("repo = ?")
        params.append(repo)
    if owner:
        clauses.append("owner = ?")
        params.append(owner)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY author_date DESC"
    if limit:
        query += f" LIMIT {int(limit)}"
    with _conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_repo_summaries() -> list[dict]:
    _init_git_tables()
    with _conn() as conn:
        rows = conn.execute("""
            SELECT
                r.full_name, r.owner, r.name, r.description, r.language,
                r.private, r.pushed_at, r.html_url,
                COUNT(c.sha) as commit_count,
                MAX(c.author_date) as last_commit_at,
                (SELECT message FROM gh_commits c2
                 WHERE c2.repo = r.name AND c2.owner = r.owner
                 ORDER BY c2.author_date DESC LIMIT 1) as last_commit_msg
            FROM gh_repos r
            LEFT JOIN gh_commits c ON c.repo = r.name AND c.owner = r.owner
            GROUP BY r.full_name
            ORDER BY r.pushed_at DESC
        """).fetchall()
    return [dict(r) for r in rows]


def get_commit_stats() -> dict:
    _init_git_tables()
    with _conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM gh_commits").fetchone()[0]
        repos = conn.execute("SELECT COUNT(*) FROM gh_repos").fetchone()[0]
        active_7d = conn.execute(
            "SELECT COUNT(*) FROM gh_commits WHERE author_date > datetime('now', '-7 days')"
        ).fetchone()[0]
        active_30d = conn.execute(
            "SELECT COUNT(*) FROM gh_commits WHERE author_date > datetime('now', '-30 days')"
        ).fetchone()[0]
        top_repos = conn.execute("""
            SELECT repo, owner, COUNT(*) as cnt
            FROM gh_commits
            GROUP BY repo, owner
            ORDER BY cnt DESC LIMIT 10
        """).fetchall()
        by_author = conn.execute("""
            SELECT author_name, COUNT(*) as cnt
            FROM gh_commits
            GROUP BY author_name
            ORDER BY cnt DESC LIMIT 10
        """).fetchall()
        last_fetch = conn.execute(
            "SELECT MAX(fetched_at) FROM gh_fetch_log"
        ).fetchone()[0]
    return {
        "total_commits": total,
        "total_repos": repos,
        "commits_last_7d": active_7d,
        "commits_last_30d": active_30d,
        "top_repos": [dict(r) for r in top_repos],
        "by_author": [dict(r) for r in by_author],
        "last_fetched": last_fetch,
        "cache_fresh": not _repos_need_refresh(),
    }
