"""
Timeline engine — classifies commits, fetches PRs, builds Plotly interactive charts.

Commit classification covers:
  - Conventional commit type  (feat/fix/chore/docs/refactor/test/ci/perf/style)
  - Merge strategy            (squash / merge-commit / rebase / direct)
  - PR linkage                (PR number from message body or (#N) refs)
  - Author classification     (human / bot / claude)
  - Impact size               (tiny <10 lines / small <50 / medium <200 / large <500 / epic 500+)
"""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
from datetime import datetime
from typing import Any

import httpx
from loguru import logger

from .db import _conn, init_db
from .git_history import GITHUB_HEADERS, _init_git_tables

# ── DB schema for PRs and enriched commits ───────────────────────────────────

def _init_timeline_tables() -> None:
    _init_git_tables()
    with _conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS gh_pull_requests (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            number          INTEGER NOT NULL,
            repo            TEXT NOT NULL,
            owner           TEXT NOT NULL,
            title           TEXT NOT NULL,
            body            TEXT DEFAULT '',
            state           TEXT DEFAULT 'closed',
            merged_at       TEXT,
            created_at      TEXT,
            closed_at       TEXT,
            base_branch     TEXT DEFAULT '',
            head_branch     TEXT DEFAULT '',
            merge_sha       TEXT DEFAULT '',
            labels          TEXT DEFAULT '[]',
            author          TEXT DEFAULT '',
            review_count    INTEGER DEFAULT 0,
            commit_count    INTEGER DEFAULT 0,
            additions       INTEGER DEFAULT 0,
            deletions       INTEGER DEFAULT 0,
            changed_files   INTEGER DEFAULT 0,
            merge_strategy  TEXT DEFAULT '',
            fetched_at      TEXT NOT NULL,
            UNIQUE(repo, owner, number)
        );

        CREATE INDEX IF NOT EXISTS idx_prs_repo    ON gh_pull_requests(repo);
        CREATE INDEX IF NOT EXISTS idx_prs_merged  ON gh_pull_requests(merged_at);
        CREATE INDEX IF NOT EXISTS idx_prs_state   ON gh_pull_requests(state);
        """)
        # Idempotent column additions
        for col, defn in [
            ("parent_count", "INTEGER DEFAULT 1"),
            ("commit_type",  "TEXT DEFAULT ''"),
            ("pr_number",    "INTEGER DEFAULT 0"),
            ("is_bot",       "INTEGER DEFAULT 0"),
            ("is_claude",    "INTEGER DEFAULT 0"),
            ("impact_size",  "TEXT DEFAULT ''"),
            ("merge_strategy", "TEXT DEFAULT ''"),
        ]:
            try:
                conn.execute(f"ALTER TABLE gh_commits ADD COLUMN {col} {defn}")
            except sqlite3.OperationalError:
                pass


# ── Commit classification (regex-based, no API calls) ────────────────────────

_CONV_TYPE_RE = re.compile(
    r'^(feat|fix|chore|docs|refactor|test|style|perf|ci|build|revert)'
    r'(?:\([^)]*\))?!?:'
)
_PR_REF_RE   = re.compile(r'#(\d+)')
_MERGE_PR_RE = re.compile(r'^Merge pull request #(\d+)', re.IGNORECASE)
_SQUASH_RE   = re.compile(r'\(#(\d+)\)\s*$', re.MULTILINE)

BOT_NAMES = {"github-actions", "dependabot", "dependabot[bot]", "github-actions[bot]", "renovate"}
CLAUDE_MARKERS = {"co-authored-by: claude", "noreply@anthropic.com", "claude sonnet", "claude opus", "claude haiku"}


def classify_commit(row: dict) -> dict:
    """Enrich a commit dict with type, PR#, merge strategy, author type, and impact."""
    msg   = row.get("message", "") or ""
    subj  = msg.split("\n")[0].strip()
    lower = msg.lower()
    name  = (row.get("author_name", "") or "").lower()
    adds  = row.get("additions", 0) or 0
    dels  = row.get("deletions", 0) or 0
    files = row.get("files_changed", 0) or 0
    total = adds + dels

    # Conventional commit type
    m = _CONV_TYPE_RE.match(subj)
    commit_type = m.group(1) if m else _infer_type(subj, lower)

    # PR number
    sq = _SQUASH_RE.search(subj)
    mp = _MERGE_PR_RE.match(subj)
    pr_number = int(sq.group(1)) if sq else (int(mp.group(1)) if mp else 0)
    if not pr_number:
        refs = _PR_REF_RE.findall(msg)
        pr_number = int(refs[0]) if refs else 0

    # Merge strategy (detected from message structure)
    parents = row.get("parent_count", 1) or 1
    if parents >= 2:
        strategy = "merge-commit"
    elif _MERGE_PR_RE.match(subj):
        strategy = "merge-commit"
    elif sq or (pr_number and not _MERGE_PR_RE.match(subj)):
        strategy = "squash"
    elif "rebase" in lower[:100]:
        strategy = "rebase"
    else:
        strategy = "direct" if not pr_number else "squash"

    # Author classification
    is_bot    = name in BOT_NAMES or "[bot]" in name
    is_claude = any(m in lower for m in CLAUDE_MARKERS)

    # Impact size
    if total == 0:
        impact = "unknown"
    elif total < 10:
        impact = "tiny"
    elif total < 50:
        impact = "small"
    elif total < 200:
        impact = "medium"
    elif total < 500:
        impact = "large"
    else:
        impact = "epic"

    return {
        **row,
        "commit_type":    commit_type,
        "pr_number":      pr_number,
        "merge_strategy": strategy,
        "is_bot":         is_bot,
        "is_claude":      is_claude,
        "impact_size":    impact,
    }


def _infer_type(subj: str, lower: str) -> str:
    subj_l = subj.lower()
    if subj_l.startswith("merge"):
        return "merge"
    if subj_l.startswith("revert"):
        return "revert"
    if any(w in subj_l for w in ("add", "implement", "create", "introduce", "new")):
        return "feat"
    if any(w in subj_l for w in ("fix", "bug", "resolve", "patch", "correct")):
        return "fix"
    if any(w in subj_l for w in ("update", "bump", "upgrade", "dependency")):
        return "chore"
    if any(w in subj_l for w in ("docs", "readme", "comment", "documentation")):
        return "docs"
    if any(w in subj_l for w in ("refactor", "clean", "restructure", "reorganize")):
        return "refactor"
    if any(w in subj_l for w in ("test", "spec", "coverage")):
        return "test"
    if any(w in subj_l for w in ("deploy", "release", "ship", "ci", "pipeline")):
        return "ci"
    return "other"


# ── Classify all cached commits in DB ────────────────────────────────────────

def enrich_all_commits() -> int:
    """Classify every unclassified commit in the DB. Returns count updated."""
    _init_timeline_tables()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM gh_commits WHERE commit_type = '' OR commit_type IS NULL"
        ).fetchall()
    if not rows:
        return 0

    enriched = [classify_commit(dict(r)) for r in rows]
    with _conn() as conn:
        conn.executemany(
            """UPDATE gh_commits SET
               commit_type=?, pr_number=?, merge_strategy=?,
               is_bot=?, is_claude=?, impact_size=?
               WHERE sha=? AND repo=?""",
            [(
                e["commit_type"], e["pr_number"], e["merge_strategy"],
                int(e["is_bot"]), int(e["is_claude"]), e["impact_size"],
                e["sha"], e["repo"],
            ) for e in enriched],
        )
    return len(enriched)


# ── PR fetch (GitHub API) ─────────────────────────────────────────────────────

async def fetch_prs_for_repo(
    client: httpx.AsyncClient, owner: str, repo: str, state: str = "all"
) -> list[dict]:
    all_prs: list[dict] = []
    page = 1
    while True:
        try:
            resp = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/pulls",
                headers=GITHUB_HEADERS,
                params={"state": state, "per_page": 100, "page": page},
                timeout=15.0,
            )
            if resp.status_code != 200:
                break
            data = resp.json()
            if not data:
                break
            all_prs.extend(data)
            if len(data) < 100:
                break
            page += 1
        except Exception as e:
            logger.warning(f"PR fetch error {owner}/{repo}: {e}")
            break
    return all_prs


def _detect_merge_strategy(pr: dict) -> str:
    """Detect squash/merge/rebase from PR title and merge commit message."""
    title = pr.get("title", "").lower()
    if "squash" in title:
        return "squash"
    # If only 1 parent on merge commit → squash or rebase; 2 → merge commit
    # We don't have parent info here, but branch naming helps
    head = pr.get("head", {}).get("ref", "")
    if re.match(r'^(feat|fix|chore|docs|refactor|test)/\d+', head):
        return "squash"
    return "merge-commit"


def _save_prs(prs: list[dict], owner: str, repo: str) -> int:
    _init_timeline_tables()
    ts = datetime.now().isoformat()
    rows = []
    for pr in prs:
        if not pr.get("merged_at") and pr.get("state") == "open":
            continue  # skip open, unmerged PRs for timeline purposes (keep closed)
        labels = json.dumps([l["name"] for l in pr.get("labels", [])])
        strategy = _detect_merge_strategy(pr)
        rows.append((
            pr["number"], repo, owner,
            pr.get("title", ""), pr.get("body", "") or "",
            pr.get("state", ""), pr.get("merged_at"),
            pr.get("created_at"), pr.get("closed_at"),
            pr.get("base", {}).get("ref", ""),
            pr.get("head", {}).get("ref", ""),
            pr.get("merge_commit_sha", "")[:7] if pr.get("merge_commit_sha") else "",
            labels,
            pr.get("user", {}).get("login", ""),
            strategy,
            ts,
        ))
    if not rows:
        return 0
    with _conn() as conn:
        conn.executemany(
            """INSERT INTO gh_pull_requests
               (number, repo, owner, title, body, state, merged_at, created_at, closed_at,
                base_branch, head_branch, merge_sha, labels, author, merge_strategy, fetched_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(repo, owner, number) DO UPDATE SET
                 state=excluded.state, merged_at=excluded.merged_at,
                 merge_strategy=excluded.merge_strategy, fetched_at=excluded.fetched_at""",
            rows,
        )
    return len(rows)


async def refresh_prs(repos: list[tuple[str, str]] | None = None) -> dict:
    """Fetch PRs for all repos (or a subset). Returns stats."""
    _init_timeline_tables()
    if repos is None:
        with _conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT owner, name FROM gh_repos ORDER BY pushed_at DESC"
            ).fetchall()
        repos = [(r["owner"], r["name"]) for r in rows]

    sem = asyncio.Semaphore(6)
    total = 0

    async def _do(client: httpx.AsyncClient, owner: str, repo: str) -> int:
        async with sem:
            prs = await fetch_prs_for_repo(client, owner, repo)
            if not prs:
                return 0
            n = _save_prs(prs, owner, repo)
            logger.debug(f"  {owner}/{repo}: {n} PRs saved")
            return n

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[_do(client, o, r) for o, r in repos])
    total = sum(results)
    logger.info(f"PR refresh done: {total} PRs saved across {len(repos)} repos")
    return {"prs_saved": total, "repos_scanned": len(repos)}


# ── Plotly timeline chart builders ───────────────────────────────────────────

def build_commit_timeline(
    repo: str | None = None,
    owner: str | None = None,
    since: str | None = None,
    group_by: str = "repo",      # "repo" | "type" | "author" | "strategy" | "impact"
    include_bots: bool = False,
) -> str:
    """Return a Plotly figure as a self-contained HTML div string."""
    import pandas as pd
    import plotly.express as px
    import plotly.graph_objects as go

    enrich_all_commits()
    _init_timeline_tables()

    query = "SELECT * FROM gh_commits WHERE 1=1"
    params: list[Any] = []
    if repo:
        query += " AND repo=?"; params.append(repo)
    if owner:
        query += " AND owner=?"; params.append(owner)
    if since:
        query += " AND author_date >= ?"; params.append(since)
    if not include_bots:
        query += " AND (is_bot=0 OR is_bot IS NULL)"
    query += " ORDER BY author_date"

    with _conn() as conn:
        rows = conn.execute(query, params).fetchall()

    if not rows:
        return "<p style='color:#64748b;padding:20px'>No commits match the selected filters.</p>"

    df = pd.DataFrame([dict(r) for r in rows])
    import warnings
    df["author_date"] = pd.to_datetime(df["author_date"], utc=True)
    df["date"]        = df["author_date"].dt.date
    df["subject"]     = df["message"].str.split("\n").str[0].str[:80]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df["week"]  = df["author_date"].dt.to_period("W").dt.start_time
        df["month"] = df["author_date"].dt.to_period("M").dt.start_time
    # Convert period-derived timestamps back to tz-aware for Plotly
    df["week"]  = pd.to_datetime(df["week"]).dt.tz_localize("UTC")
    df["month"] = pd.to_datetime(df["month"]).dt.tz_localize("UTC")

    # ── Chart 1: Commit activity over time (bar chart by week) ──────────────
    color_map = {
        "feat": "#22c55e", "fix": "#ef4444", "chore": "#64748b",
        "docs": "#3b82f6", "refactor": "#a855f7", "test": "#f59e0b",
        "ci": "#06b6d4", "perf": "#f97316", "build": "#8b5cf6",
        "merge": "#94a3b8", "revert": "#ec4899", "other": "#475569",
        "style": "#d1d5db",
    }
    strategy_colors = {
        "squash": "#22c55e", "merge-commit": "#3b82f6",
        "rebase": "#a855f7", "direct": "#f59e0b",
    }
    impact_colors = {
        "tiny": "#1e3a5f", "small": "#1d4ed8", "medium": "#22c55e",
        "large": "#f59e0b", "epic": "#ef4444", "unknown": "#334155",
    }

    color_col = {
        "repo": "repo", "type": "commit_type", "author": "author_name",
        "strategy": "merge_strategy", "impact": "impact_size",
    }.get(group_by, "commit_type")
    color_discrete = {
        "type": color_map, "strategy": strategy_colors, "impact": impact_colors,
    }.get(group_by, {})

    weekly = df.groupby(["week", color_col]).size().reset_index(name="count")
    weekly["week_str"] = weekly["week"].astype(str)

    fig1 = px.bar(
        weekly, x="week", y="count", color=color_col,
        title=f"Commit Activity by Week — grouped by {group_by}",
        color_discrete_map=color_discrete if color_discrete else None,
        labels={"week": "Week", "count": "Commits", color_col: group_by.title()},
        template="plotly_dark",
    )
    fig1.update_layout(
        plot_bgcolor="#1a1d27", paper_bgcolor="#1a1d27",
        font=dict(color="#e2e8f0", size=12),
        legend=dict(bgcolor="#252836", bordercolor="#2e3148", borderwidth=1),
        margin=dict(l=40, r=20, t=50, b=40),
        height=320,
        barmode="stack",
    )

    # ── Chart 2: Commit type breakdown (pie) ─────────────────────────────────
    type_counts = df["commit_type"].value_counts().reset_index()
    type_counts.columns = ["type", "count"]
    fig2 = px.pie(
        type_counts, names="type", values="count",
        title="Commit Type Distribution",
        color="type", color_discrete_map=color_map,
        template="plotly_dark",
        hole=0.4,
    )
    fig2.update_layout(
        plot_bgcolor="#1a1d27", paper_bgcolor="#1a1d27",
        font=dict(color="#e2e8f0", size=11),
        margin=dict(l=20, r=20, t=50, b=20),
        height=300,
        legend=dict(bgcolor="#252836"),
    )

    # ── Chart 3: Merge strategy breakdown (pie) ───────────────────────────────
    strategy_counts = df["merge_strategy"].value_counts().reset_index()
    strategy_counts.columns = ["strategy", "count"]
    fig3 = px.pie(
        strategy_counts, names="strategy", values="count",
        title="Merge Strategy Distribution",
        color="strategy", color_discrete_map=strategy_colors,
        template="plotly_dark",
        hole=0.4,
    )
    fig3.update_layout(
        plot_bgcolor="#1a1d27", paper_bgcolor="#1a1d27",
        font=dict(color="#e2e8f0", size=11),
        margin=dict(l=20, r=20, t=50, b=20),
        height=300,
        legend=dict(bgcolor="#252836"),
    )

    # ── Chart 4: Impact size timeline ─────────────────────────────────────────
    impact_weekly = df.groupby(["week", "impact_size"]).size().reset_index(name="count")
    fig4 = px.bar(
        impact_weekly, x="week", y="count", color="impact_size",
        title="Commit Impact Size Over Time",
        color_discrete_map=impact_colors,
        labels={"week": "Week", "count": "Commits", "impact_size": "Impact"},
        template="plotly_dark",
        barmode="stack",
    )
    fig4.update_layout(
        plot_bgcolor="#1a1d27", paper_bgcolor="#1a1d27",
        font=dict(color="#e2e8f0", size=11),
        margin=dict(l=40, r=20, t=50, b=40),
        height=280,
        legend=dict(bgcolor="#252836"),
    )

    # ── Chart 5: Claude vs Human vs Bot authorship ───────────────────────────
    def author_class(row: dict) -> str:
        if row.get("is_claude"): return "Claude AI"
        if row.get("is_bot"):    return "Bot/CI"
        return "Human"
    df["author_class"] = df.apply(author_class, axis=1)
    auth_weekly = df.groupby(["week", "author_class"]).size().reset_index(name="count")
    fig5 = px.bar(
        auth_weekly, x="week", y="count", color="author_class",
        title="Author Type Over Time (Human / Claude AI / Bot)",
        color_discrete_map={"Human": "#3b82f6", "Claude AI": "#a855f7", "Bot/CI": "#64748b"},
        template="plotly_dark",
        barmode="stack",
    )
    fig5.update_layout(
        plot_bgcolor="#1a1d27", paper_bgcolor="#1a1d27",
        font=dict(color="#e2e8f0", size=11),
        margin=dict(l=40, r=20, t=50, b=40),
        height=280,
        legend=dict(bgcolor="#252836"),
    )

    # ── Chart 6: Scatter — additions vs deletions colored by type ────────────
    sample = df[df["additions"] + df["deletions"] < 2000].copy()
    if not sample.empty:
        sample["total_changes"] = sample["additions"] + sample["deletions"]
        fig6 = px.scatter(
            sample, x="author_date", y="total_changes",
            color="commit_type", size_max=15,
            title="Change Volume by Commit (lines added + deleted)",
            color_discrete_map=color_map,
            hover_data={"subject": True, "repo": True, "author_name": True, "author_date": False},
            labels={"author_date": "Date", "total_changes": "Lines Changed", "commit_type": "Type"},
            template="plotly_dark",
        )
        fig6.update_layout(
            plot_bgcolor="#1a1d27", paper_bgcolor="#1a1d27",
            font=dict(color="#e2e8f0", size=11),
            margin=dict(l=40, r=20, t=50, b=40),
            height=300,
            legend=dict(bgcolor="#252836"),
        )
        chart6_html = fig6.to_html(full_html=False, include_plotlyjs=False)
    else:
        chart6_html = ""

    # ── Stats summary ─────────────────────────────────────────────────────────
    claude_pct = round(100 * df["is_claude"].sum() / len(df), 1) if len(df) else 0
    top_type   = df["commit_type"].value_counts().index[0] if len(df) else "—"
    top_strat  = df["merge_strategy"].value_counts().index[0] if len(df) else "—"
    date_range = f"{df['author_date'].min().strftime('%Y-%m-%d')} → {df['author_date'].max().strftime('%Y-%m-%d')}"

    # Combine all charts into one HTML fragment
    return f"""
<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px;
            background:var(--surface2);border-radius:8px;padding:14px;border:1px solid var(--border)">
  <div><div style="font-size:22px;font-weight:800;color:#22c55e">{len(df):,}</div>
       <div style="font-size:11px;color:var(--muted)">Commits analysed</div></div>
  <div><div style="font-size:22px;font-weight:800;color:#a855f7">{claude_pct}%</div>
       <div style="font-size:11px;color:var(--muted)">Claude-assisted</div></div>
  <div><div style="font-size:22px;font-weight:800;color:#3b82f6">{top_type}</div>
       <div style="font-size:11px;color:var(--muted)">Most common type</div></div>
  <div><div style="font-size:18px;font-weight:700;color:#f59e0b">{top_strat}</div>
       <div style="font-size:11px;color:var(--muted)">Primary merge strategy</div></div>
  <div><div style="font-size:13px;font-weight:600;color:#94a3b8">{date_range}</div>
       <div style="font-size:11px;color:var(--muted)">Date range</div></div>
  <div><div style="font-size:18px;font-weight:700;color:#06b6d4">{df['repo'].nunique()}</div>
       <div style="font-size:11px;color:var(--muted)">Repos in view</div></div>
</div>
<div style="display:grid;grid-template-columns:1fr;gap:12px">
  {fig1.to_html(full_html=False, include_plotlyjs=False)}
  {fig5.to_html(full_html=False, include_plotlyjs=False)}
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
    {fig2.to_html(full_html=False, include_plotlyjs=False)}
    {fig3.to_html(full_html=False, include_plotlyjs=False)}
  </div>
  {fig4.to_html(full_html=False, include_plotlyjs=False)}
  {chart6_html}
</div>
"""


def build_pr_timeline(repo: str | None = None, owner: str | None = None) -> str:
    """
    PR shipping analytics — answers:
      1. How many PRs are you shipping per week? (velocity)
      2. What kind of PRs? (deploy vs feature vs fix vs chore)
      3. Which repos are most active?
      4. How has your merge strategy evolved?
      5. Which PRs took longest — only the non-zero-day ones worth showing.

    Note: 94% of PRs merge same-day (fast CI + squash workflow),
    so a Gantt timeline shows nothing useful — this data tells a better story.
    """
    import warnings
    import pandas as pd
    import plotly.express as px
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    _init_timeline_tables()
    query = """
        SELECT *,
               julianday(merged_at) - julianday(created_at) as days_open
        FROM gh_pull_requests
        WHERE merged_at IS NOT NULL AND created_at IS NOT NULL
    """
    params: list[Any] = []
    if repo:
        query += " AND repo=?"; params.append(repo)
    if owner:
        query += " AND owner=?"; params.append(owner)

    with _conn() as conn:
        rows = conn.execute(query, params).fetchall()

    if not rows:
        return "<p style='color:#64748b;padding:20px'>No merged PR data yet. Click '↻ Fetch PRs' above.</p>"

    df = pd.DataFrame([dict(r) for r in rows])
    df["merged_at"]  = pd.to_datetime(df["merged_at"], utc=True)
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    df["days_open"]  = df["days_open"].fillna(0).round(1)

    # Classify PR type from title
    def pr_type(title: str) -> str:
        t = (title or "").lower()
        if any(w in t for w in ("deploy", "ship", "prod", "release", "→")):
            return "deploy"
        if t.startswith("feat") or "add " in t[:20] or "implement" in t[:30]:
            return "feature"
        if t.startswith("fix") or "bug" in t[:20] or "resolv" in t[:20]:
            return "fix"
        if t.startswith("chore") or "bump" in t[:20] or "update dep" in t[:30]:
            return "chore"
        if t.startswith("refactor") or t.startswith("clean"):
            return "refactor"
        if t.startswith("docs") or "readme" in t[:20]:
            return "docs"
        return "other"

    df["pr_type"] = df["title"].apply(pr_type)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df["week"]  = df["merged_at"].dt.to_period("W").dt.start_time
        df["month"] = df["merged_at"].dt.to_period("M").dt.start_time
    df["week"]  = pd.to_datetime(df["week"]).dt.tz_localize("UTC")
    df["month"] = pd.to_datetime(df["month"]).dt.tz_localize("UTC")

    type_colors = {
        "deploy": "#3b82f6", "feature": "#22c55e", "fix": "#ef4444",
        "chore": "#64748b", "refactor": "#a855f7", "docs": "#f59e0b", "other": "#475569",
    }
    strategy_colors = {
        "squash": "#22c55e", "merge-commit": "#3b82f6",
        "rebase": "#a855f7", "direct": "#f59e0b",
    }

    # ── Chart 1: PR velocity per week, stacked by type ──────────────────────
    weekly = df.groupby(["week", "pr_type"]).size().reset_index(name="count")
    fig1 = px.bar(
        weekly, x="week", y="count", color="pr_type",
        title="PRs Shipped Per Week — by Type",
        color_discrete_map=type_colors,
        labels={"week": "Week", "count": "PRs Merged", "pr_type": "PR Type"},
        template="plotly_dark",
        barmode="stack",
    )
    fig1.update_layout(
        plot_bgcolor="#1a1d27", paper_bgcolor="#1a1d27",
        font=dict(color="#e2e8f0", size=11),
        margin=dict(l=40, r=20, t=50, b=40),
        height=300, legend=dict(bgcolor="#252836"),
    )

    # ── Chart 2: PR type breakdown (donut) ───────────────────────────────────
    type_counts = df["pr_type"].value_counts().reset_index()
    type_counts.columns = ["type", "count"]
    fig2 = px.pie(
        type_counts, names="type", values="count",
        title="What Kind of PRs?",
        color="type", color_discrete_map=type_colors,
        template="plotly_dark", hole=0.45,
    )
    fig2.update_layout(
        plot_bgcolor="#1a1d27", paper_bgcolor="#1a1d27",
        font=dict(color="#e2e8f0", size=11),
        margin=dict(l=20, r=20, t=50, b=20),
        height=300, legend=dict(bgcolor="#252836"),
    )
    fig2.update_traces(
        hovertemplate="<b>%{label}</b><br>%{value} PRs (%{percent})<extra></extra>"
    )

    # ── Chart 3: Top repos by PR count (horizontal bar) ──────────────────────
    repo_counts = df.groupby("repo").size().reset_index(name="count").sort_values("count")
    repo_counts = repo_counts.tail(15)  # top 15
    fig3 = px.bar(
        repo_counts, x="count", y="repo", orientation="h",
        title="Most Active Repos (by merged PRs)",
        template="plotly_dark",
        labels={"count": "Merged PRs", "repo": ""},
        color="count",
        color_continuous_scale=[[0, "#1e3a5f"], [1, "#3b82f6"]],
    )
    fig3.update_layout(
        plot_bgcolor="#1a1d27", paper_bgcolor="#1a1d27",
        font=dict(color="#e2e8f0", size=11),
        margin=dict(l=10, r=20, t=50, b=40),
        height=350, showlegend=False,
        coloraxis_showscale=False,
    )

    # ── Chart 4: Merge strategy over time ────────────────────────────────────
    monthly_strat = df.groupby(["month", "merge_strategy"]).size().reset_index(name="count")
    fig4 = px.bar(
        monthly_strat, x="month", y="count", color="merge_strategy",
        title="Merge Strategy Over Time — Are You Moving to Squash?",
        color_discrete_map=strategy_colors,
        labels={"month": "Month", "count": "PRs", "merge_strategy": "Strategy"},
        template="plotly_dark",
        barmode="stack",
    )
    fig4.update_layout(
        plot_bgcolor="#1a1d27", paper_bgcolor="#1a1d27",
        font=dict(color="#e2e8f0", size=11),
        margin=dict(l=40, r=20, t=50, b=40),
        height=280, legend=dict(bgcolor="#252836"),
    )

    # ── Chart 5: PRs that actually took time (>0 days) — these are the real ones ──
    slow_prs = df[df["days_open"] > 0.5].copy()
    if not slow_prs.empty:
        slow_prs = slow_prs.sort_values("days_open", ascending=False).head(40)
        slow_prs["label"] = "#" + slow_prs["number"].astype(str) + " " + slow_prs["title"].str[:45]
        fig5 = px.bar(
            slow_prs, x="days_open", y="label", orientation="h",
            title=f"PRs That Took >12 Hours to Merge ({len(slow_prs)} total) — These Are Your Real Review Cycles",
            color="pr_type", color_discrete_map=type_colors,
            labels={"days_open": "Days Open", "label": "", "pr_type": "Type"},
            template="plotly_dark",
            hover_data={"repo": True, "merge_strategy": True, "author": True},
        )
        fig5.update_layout(
            plot_bgcolor="#1a1d27", paper_bgcolor="#1a1d27",
            font=dict(color="#e2e8f0", size=11),
            margin=dict(l=10, r=20, t=60, b=40),
            height=max(300, min(900, 25 * len(slow_prs))),
            legend=dict(bgcolor="#252836"),
        )
        chart5_html = fig5.to_html(full_html=False, include_plotlyjs=False)
    else:
        chart5_html = "<p style='color:#64748b;padding:16px'>All PRs merged same-day — no slow PRs to show.</p>"

    # ── Stats summary ─────────────────────────────────────────────────────────
    total_prs     = len(df)
    deploy_prs    = (df["pr_type"] == "deploy").sum()
    feature_prs   = (df["pr_type"] == "feature").sum()
    fix_prs       = (df["pr_type"] == "fix").sum()
    slow_count    = (df["days_open"] > 0.5).sum()
    top_repo      = df["repo"].value_counts().index[0] if len(df) else "—"
    top_strat     = df["merge_strategy"].value_counts().index[0] if len(df) else "—"
    prs_per_week  = round(len(df) / max((df["merged_at"].max() - df["merged_at"].min()).days / 7, 1), 1)

    return f"""
<div style="margin-bottom:12px;background:var(--surface2);border-radius:8px;padding:14px;border:1px solid var(--border)">
  <div style="font-size:12px;color:var(--muted);margin-bottom:10px">
    <strong style="color:#e2e8f0">What this shows:</strong>
    Your PR shipping cadence, what kinds of work you're merging, which repos are most active,
    and whether your merge strategy is consistent. The Gantt was useless here — {total_prs - slow_count:,} of {total_prs:,} PRs merged same-day,
    so a timeline would show {total_prs - slow_count:,} invisible bars. These charts tell the real story.
  </div>
  <div style="display:flex;gap:12px;flex-wrap:wrap">
    <div class="stat"><div style="font-size:22px;font-weight:800;color:#22c55e">{total_prs:,}</div><div style="font-size:11px;color:var(--muted)">Total merged PRs</div></div>
    <div class="stat"><div style="font-size:22px;font-weight:800;color:#f59e0b">{prs_per_week}</div><div style="font-size:11px;color:var(--muted)">PRs/week avg</div></div>
    <div class="stat"><div style="font-size:22px;font-weight:800;color:#3b82f6">{deploy_prs}</div><div style="font-size:11px;color:var(--muted)">Deploy PRs</div></div>
    <div class="stat"><div style="font-size:22px;font-weight:800;color:#22c55e">{feature_prs}</div><div style="font-size:11px;color:var(--muted)">Feature PRs</div></div>
    <div class="stat"><div style="font-size:22px;font-weight:800;color:#ef4444">{fix_prs}</div><div style="font-size:11px;color:var(--muted)">Fix PRs</div></div>
    <div class="stat"><div style="font-size:22px;font-weight:800;color:#a855f7">{slow_count}</div><div style="font-size:11px;color:var(--muted)">PRs &gt;12hr open</div></div>
    <div class="stat"><div style="font-size:16px;font-weight:700;color:#94a3b8">{top_repo}</div><div style="font-size:11px;color:var(--muted)">Most active repo</div></div>
    <div class="stat"><div style="font-size:16px;font-weight:700;color:#22c55e">{top_strat}</div><div style="font-size:11px;color:var(--muted)">Primary strategy</div></div>
  </div>
</div>
<div style="display:grid;grid-template-columns:1fr;gap:12px">
  {fig1.to_html(full_html=False, include_plotlyjs=False)}
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
    {fig2.to_html(full_html=False, include_plotlyjs=False)}
    {fig3.to_html(full_html=False, include_plotlyjs=False)}
  </div>
  {fig4.to_html(full_html=False, include_plotlyjs=False)}
  {chart5_html}
</div>
"""


# ── Query helpers ─────────────────────────────────────────────────────────────

def get_pr_list(repo: str | None = None, limit: int = 200) -> list[dict]:
    _init_timeline_tables()
    query = "SELECT * FROM gh_pull_requests WHERE merged_at IS NOT NULL"
    params: list[Any] = []
    if repo:
        query += " AND repo=?"; params.append(repo)
    query += " ORDER BY merged_at DESC LIMIT ?"
    params.append(limit)
    with _conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_commit_type_stats(repo: str | None = None) -> dict:
    _init_timeline_tables()
    enrich_all_commits()
    query = "SELECT commit_type, merge_strategy, is_claude, is_bot, impact_size, COUNT(*) as cnt FROM gh_commits"
    params: list[Any] = []
    if repo:
        query += " WHERE repo=?"; params.append(repo)
    query += " GROUP BY commit_type, merge_strategy, is_claude, is_bot, impact_size"
    with _conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return {"breakdown": [dict(r) for r in rows]}
