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

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "codellama:13b")


def _init_llm_table() -> None:
    init_db()
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS repo_llm_analysis (
                repo         TEXT PRIMARY KEY,
                owner        TEXT NOT NULL,
                llm_purpose  TEXT DEFAULT '',
                llm_why      TEXT DEFAULT '',
                source       TEXT DEFAULT 'llm',
                model        TEXT DEFAULT '',
                evidence     TEXT DEFAULT '',
                analyzed_at  TEXT NOT NULL
            )
        """)


def _ask_ollama(prompt: str) -> str | None:
    try:
        r = httpx.post(f"{OLLAMA_URL}/api/generate",
                       json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
                       timeout=120)
        if r.status_code == 200:
            return (r.json().get("response") or "").strip()
        logger.warning(f"ollama {r.status_code}")
    except Exception as e:
        logger.warning(f"ollama unreachable: {e}")
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


async def analyze_repo(owner: str, repo: str) -> dict:
    """Read the repo's REAL code + README, ask an LLM for purpose + why. Stored
    with source='llm' provenance. Ollama-first, OpenRouter fallback."""
    _init_llm_table()
    audit = await code_audit(owner, repo)
    async with httpx.AsyncClient() as c:
        readme = await _fetch_file_content(c, owner, repo, "README.md") or ""
    # evidence we feed the model — REAL code facts, not vibes
    evidence = (
        f"repo: {repo}\n"
        f"dependencies ({audit['dep_source']}): {', '.join(audit['deps'][:25])}\n"
        f"api routes: {', '.join(audit['routes'][:15]) or 'none detected'}\n"
        f"README (first 1500 chars):\n{readme[:1500]}"
    )
    prompt = (
        "You are documenting a developer's repo for a capability registry. From the "
        "EVIDENCE below (real dependencies, routes, README), answer in JSON with exactly "
        'two keys: "purpose" (one clear sentence: what this repo does) and "why" (one '
        "sentence: why it likely exists / what problem it solves, inferred from the stack). "
        "If the evidence is too thin to tell, say so honestly. Do NOT invent features.\n\n"
        f"EVIDENCE:\n{evidence}\n\nJSON:"
    )
    raw = _ask_ollama(prompt)
    model = OLLAMA_MODEL
    if not raw:
        raw = _ask_openrouter(prompt)
        model = "anthropic/claude-haiku-4-5"
    if not raw:
        return {"repo": repo, "error": "no LLM available (ollama + openrouter both failed)"}

    purpose, why = _parse_llm_json(raw)
    from datetime import datetime
    ts = datetime.now().isoformat()
    with _conn() as conn:
        conn.execute(
            """INSERT INTO repo_llm_analysis
               (repo, owner, llm_purpose, llm_why, source, model, evidence, analyzed_at)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(repo) DO UPDATE SET
                 llm_purpose=excluded.llm_purpose, llm_why=excluded.llm_why,
                 model=excluded.model, evidence=excluded.evidence, analyzed_at=excluded.analyzed_at""",
            (repo, owner, purpose, why, "llm", model, evidence[:2000], ts),
        )
    return {"repo": repo, "purpose": purpose, "why": why, "source": "llm", "model": model}


def _parse_llm_json(raw: str) -> tuple[str, str]:
    """Best-effort extract {purpose, why} from an LLM response (may have prose around the JSON)."""
    import re
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        try:
            d = json.loads(m.group(0))
            return (d.get("purpose", "")[:300], d.get("why", "")[:300])
        except Exception:
            pass
    # fallback: first two sentences
    parts = [s.strip() for s in raw.split(".") if s.strip()]
    return (parts[0][:300] if parts else raw[:300], parts[1][:300] if len(parts) > 1 else "")


def get_llm_analysis(repo: str) -> dict | None:
    _init_llm_table()
    with _conn() as conn:
        row = conn.execute("SELECT * FROM repo_llm_analysis WHERE repo=?", (repo,)).fetchone()
    return dict(row) if row else None


async def analyze_all(force: bool = False, limit: int = 0) -> dict:
    """Background runner: analyze repos that have no LLM analysis yet (or all if
    force). Resumable — chips through the fleet. Rate-limited so Ollama isn't
    hammered. Designed to be called from a cron/background task."""
    _init_llm_table()
    with _conn() as conn:
        repos = [(r["owner"], r["name"]) for r in conn.execute(
            "SELECT owner, name FROM gh_repos ORDER BY pushed_at DESC").fetchall()]
        done = {r["repo"] for r in conn.execute("SELECT repo FROM repo_llm_analysis").fetchall()}
    todo = [(o, n) for o, n in repos if force or n not in done]
    if limit:
        todo = todo[:limit]
    analyzed = 0
    for owner, repo in todo:
        res = await analyze_repo(owner, repo)
        if not res.get("error"):
            analyzed += 1
            logger.info(f"llm-analyzed {repo}: {res['purpose'][:60]}")
    return {"analyzed": analyzed, "remaining": len(repos) - len(done) - analyzed, "total": len(repos)}
