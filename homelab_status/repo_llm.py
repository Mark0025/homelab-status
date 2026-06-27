"""LLM analysis of repos — synthesize a real purpose + 'why' from the ACTUAL
code, for the ~35% of repos whose README is thin/empty (the gap the capability
registry can't fill deterministically). The CODE_ANAYLZER idea, without reviving
that dead repo: reuse the app's own _fetch_file_content + an LLM.

Ollama-first (free, local, on the homelab at ollama:11434 with codellama:13b /
mistral:7b) with OpenRouter fallback. Runs as a resumable BACKGROUND runner (like
refresh_all) so it chips through all 133 repos over time.

DISCIPLINE: LLM output is SYNTHESIS, not fact. Everything is stored with
source="llm" + the model + analyzed_at, and grounded in real code excerpts so a
reader can tell an inferred purpose from a README-quoted one (synthesis rule).
"""

import json
import os
import urllib.request as _req

import httpx
from loguru import logger

from .db import _conn, init_db
from .project_intel import code_audit, _fetch_file_content
from .git_history import GITHUB_HEADERS

# Mark's own gateway: go-local-aibot (container `claude-http`) — one
# OpenAI-compatible API wrapping the host's real `claude` CLI (Claude Max) and,
# optionally, local models by `local:` prefix. 'claude-fast:haiku' = the "lean
# Claude" Mark pointed at. Reachable by name on the homelab network. This REPLACES
# the slow/flaky local-Ollama approach — consume the gateway Mark built for exactly
# this, don't reinvent.
CLAUDE_HTTP_URL = os.environ.get("CLAUDE_HTTP_URL", "http://claude-http:8765")
ANALYSIS_MODEL = os.environ.get("ANALYSIS_MODEL", "claude-fast:haiku")


def _init_llm_table() -> None:
    """APPEND-ONLY analysis snapshots. Each run adds a dated row (never overwrites)
    so we keep a TIMELINE of perspectives — the foundation of the daily honesty
    loop (#52). The API returns the LATEST by default; history is available too.
    LLM output is synthesis, dated + source-flagged, never presented as ground truth."""
    init_db()
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS repo_llm_analysis (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                repo         TEXT NOT NULL,
                owner        TEXT NOT NULL,
                llm_purpose  TEXT DEFAULT '',
                llm_why      TEXT DEFAULT '',
                lens         TEXT DEFAULT 'baseline',   -- the perspective of this run (#52)
                grade        TEXT DEFAULT '',
                maturity     TEXT DEFAULT '',
                source       TEXT DEFAULT 'llm',         -- always 'llm' — AI-built, may be off
                model        TEXT DEFAULT '',
                evidence     TEXT DEFAULT '',
                analyzed_at  TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_repo_date "
                     "ON repo_llm_analysis(repo, analyzed_at DESC)")
        # migrate an OLD overwrite-style table (repo as PRIMARY KEY, no id/lens) if present
        cols = {r[1] for r in conn.execute("PRAGMA table_info(repo_llm_analysis)")}
        if "id" not in cols:
            conn.execute("ALTER TABLE repo_llm_analysis RENAME TO repo_llm_analysis_old")
            conn.execute("""
                CREATE TABLE repo_llm_analysis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, repo TEXT NOT NULL, owner TEXT NOT NULL,
                    llm_purpose TEXT DEFAULT '', llm_why TEXT DEFAULT '', lens TEXT DEFAULT 'baseline',
                    grade TEXT DEFAULT '', maturity TEXT DEFAULT '', source TEXT DEFAULT 'llm',
                    model TEXT DEFAULT '', evidence TEXT DEFAULT '', analyzed_at TEXT NOT NULL)
            """)
            conn.execute("""INSERT INTO repo_llm_analysis
                (repo, owner, llm_purpose, llm_why, source, model, evidence, analyzed_at)
                SELECT repo, owner, llm_purpose, llm_why, source, model, evidence, analyzed_at
                FROM repo_llm_analysis_old""")
            conn.execute("DROP TABLE repo_llm_analysis_old")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_repo_date "
                         "ON repo_llm_analysis(repo, analyzed_at DESC)")


def _ask_claude_http(prompt: str) -> str | None:
    """Ask Mark's claude-http gateway (OpenAI-compatible). Default model is the
    'lean Claude' (claude-fast:haiku) — fast + real Claude quality."""
    try:
        r = httpx.post(f"{CLAUDE_HTTP_URL}/v1/chat/completions",
                       json={"model": ANALYSIS_MODEL,
                             "messages": [{"role": "user", "content": prompt}]},
                       timeout=90)
        if r.status_code == 200:
            return (r.json()["choices"][0]["message"]["content"] or "").strip()
        logger.warning(f"claude-http {r.status_code}")
    except Exception as e:
        logger.warning(f"claude-http unreachable: {e}")
    return None


def _ask_openrouter(prompt: str) -> str | None:
    from .journey import load_env_key
    key = load_env_key("OPENROUTER_API_KEY")
    if not key:
        return None
    try:
        payload = json.dumps({"model": "anthropic/claude-haiku-4-5", "max_tokens": 600,
                              "messages": [{"role": "user", "content": prompt}]}).encode()
        req = _req.Request("https://openrouter.ai/api/v1/chat/completions", data=payload,
                           headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                    "HTTP-Referer": "https://homelab-status.local"})
        with _req.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning(f"openrouter failed: {e}")
    return None


# The daily honesty loop (#52) rotates these lenses — a different perspective each
# day, so the timeline of snapshots gets sharper. 'baseline' is the default.
LENSES = {
    "baseline": "Document what this repo does and why, plainly.",
    "efficiency": "From the view of someone who wants to USE these tools as efficiently as "
                  "possible: what is the ONE thing that would make this repo better/more useful?",
    "gaps": "What is MISSING or half-built here that the evidence reveals?",
    "reuse": "What could another repo or an AI agent REUSE from this one?",
    "risk": "What is the biggest risk or fragility in this repo (security, maintenance, drift)?",
}


async def analyze_repo(owner: str, repo: str, lens: str = "baseline") -> dict:
    """Read the repo's REAL code + README, ask the LLM for purpose/why/grade/maturity
    under a given LENS. APPENDS a dated snapshot (never overwrites). claude-http
    gateway first, OpenRouter fallback. Output is AI synthesis, dated + flagged."""
    _init_llm_table()
    lens_instr = LENSES.get(lens, LENSES["baseline"])
    audit = await code_audit(owner, repo)
    async with httpx.AsyncClient() as c:
        readme = await _fetch_file_content(c, owner, repo, "README.md") or ""
    evidence = (
        f"repo: {repo}\n"
        f"dependencies ({audit['dep_source']}): {', '.join(audit['deps'][:25])}\n"
        f"api routes: {', '.join(audit['routes'][:15]) or 'none detected'}\n"
        f"README (first 1800 chars):\n{readme[:1800]}"
    )
    prompt = (
        "# IDENTITY\nYou are an expert software analyst documenting a repo for a capability "
        "registry. You work ONLY from the evidence and never invent features.\n\n"
        f"# LENS FOR THIS PASS\n{lens_instr}\n\n"
        "# OUTPUT — ONLY this JSON:\n"
        '{ "purpose": "1-2 sentences: what it does", '
        '"why": "1 sentence: why it exists / problem solved (answer THROUGH the lens above)", '
        '"maturity": "prototype|working|production|abandoned|empty", '
        '"grade": "A-F (completeness/polish from the evidence)" }\n'
        "If evidence is too thin: maturity='empty', grade='F'. NEVER invent.\n\n"
        f"# EVIDENCE\n{evidence}\n\n# JSON:"
    )
    raw = _ask_claude_http(prompt)
    model = ANALYSIS_MODEL
    if not raw:
        raw = _ask_openrouter(prompt)
        model = "anthropic/claude-haiku-4-5"
    if not raw:
        return {"repo": repo, "error": "no LLM available (claude-http + openrouter both failed)"}

    purpose, why, grade, maturity = _parse_llm_json(raw)
    from datetime import datetime
    ts = datetime.now().isoformat()
    with _conn() as conn:
        # APPEND a new dated snapshot — never overwrite (timeline, #52).
        conn.execute(
            """INSERT INTO repo_llm_analysis
               (repo, owner, llm_purpose, llm_why, lens, grade, maturity, source, model, evidence, analyzed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (repo, owner, purpose, why, lens, grade, maturity, "llm", model, evidence[:2000], ts),
        )
    return {"repo": repo, "purpose": purpose, "why": why, "lens": lens,
            "grade": grade, "maturity": maturity, "source": "llm", "model": model,
            "analyzed_at": ts}


def _parse_llm_json(raw: str) -> tuple[str, str, str, str]:
    """Extract (purpose, why, grade, maturity) from an LLM response (prose-tolerant)."""
    import re
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        try:
            d = json.loads(m.group(0))
            return (d.get("purpose", "")[:300], d.get("why", "")[:300],
                    str(d.get("grade", ""))[:4], str(d.get("maturity", ""))[:20])
        except Exception:
            pass
    parts = [s.strip() for s in raw.split(".") if s.strip()]
    return (parts[0][:300] if parts else raw[:300],
            parts[1][:300] if len(parts) > 1 else "", "", "")


def get_llm_analysis(repo: str) -> dict | None:
    """The LATEST analysis snapshot for a repo (what the UI/API show by default)."""
    _init_llm_table()
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM repo_llm_analysis WHERE repo=? ORDER BY analyzed_at DESC LIMIT 1",
            (repo,)).fetchone()
    return dict(row) if row else None


def get_analysis_history(repo: str, limit: int = 30) -> list[dict]:
    """All snapshots for a repo, newest first — the timeline of perspectives (#52)."""
    _init_llm_table()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM repo_llm_analysis WHERE repo=? ORDER BY analyzed_at DESC LIMIT ?",
            (repo, limit)).fetchall()
    return [dict(r) for r in rows]


async def analyze_all(force: bool = False, limit: int = 0, lens: str = "baseline") -> dict:
    """Background runner: append a snapshot per repo under `lens`. Resumable —
    skips repos already analyzed UNDER THIS LENS TODAY (so a daily cron does one
    fresh pass per lens without re-doing today's work). force=True ignores that.
    Designed for a daily cron rotating lenses (#52)."""
    _init_llm_table()
    from datetime import datetime
    today = datetime.now().date().isoformat()
    with _conn() as conn:
        repos = [(r["owner"], r["name"]) for r in conn.execute(
            "SELECT owner, name FROM gh_repos ORDER BY pushed_at DESC").fetchall()]
        # already done THIS lens TODAY (don't redo within a day)
        done = {r["repo"] for r in conn.execute(
            "SELECT DISTINCT repo FROM repo_llm_analysis WHERE lens=? AND analyzed_at >= ?",
            (lens, today)).fetchall()}
    todo = [(o, n) for o, n in repos if force or n not in done]
    if limit:
        todo = todo[:limit]
    analyzed = 0
    for owner, repo in todo:
        res = await analyze_repo(owner, repo, lens=lens)
        if not res.get("error"):
            analyzed += 1
            logger.info(f"llm-analyzed [{lens}] {repo}: {res['purpose'][:50]}")
    return {"lens": lens, "analyzed": analyzed,
            "remaining": len(repos) - len(done) - analyzed, "total": len(repos)}
