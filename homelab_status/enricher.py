"""
Deep enrichment — replaces generic template questions with specific ones.

For each repo episode:
  1. Load commit history from journey_v1.json (already captured)
  2. Scan PAI learnings for any that mention this repo
  3. Scan repo .md files on disk (DEV_MAN/plans, CLAUDE.md, etc.) with real git dates
  4. Query mdops DB for docs, using git log to verify they were written during the repo's active period
  5. Pick 3 signal commits: first, biggest pivot, last
  6. Rewrite questions with real dates, real commit messages, real context

This is idempotent — run it again and it overwrites questions.
It never touches journey_repos (the immutable archive).
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from loguru import logger

from .db import _conn, init_db
from .mdops import docs_for_repo, get_doc

JOURNEY_JSON = Path(__file__).parent.parent / "data" / "journey_v1.json"
PAI_LEARNINGS = Path.home() / ".claude" / "context" / "learnings"

# Where local repo clones might live
_LOCAL_SEARCH_ROOTS = [
    Path.home() / "Desktop" / "git-projects",
    Path.home() / "Desktop" / "pete",
    Path.home() / "00Myhomelab",
    Path.home() / "WebstormProjects",
    Path.home() / "Desktop",
]

# Doc filenames that signal vision/plan content (checked against filename, not full path)
# Intentionally excludes bare "readme" — every repo has one; prefer substantive plan docs
_PLAN_SIGNALS = re.compile(
    r"(plan|vision|roadmap|spec|mcv|goals?|strategy|claude|what.user.actually|"
    r"what.we.built|whats.working|changelog|dev.man|analysis|launch|telos|todo)",
    re.I,
)

# Honest user-intent docs — retrospective analyses of what was wanted vs what shipped
_HIGH_SIGNAL = re.compile(
    r"(what.user|what.we.built|strategic|vision|mcv|goals|reality|user.actually)",
    re.I,
)

# ── helpers ──────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_json() -> dict:
    with open(JOURNEY_JSON) as f:
        return json.load(f)


def _buffered_start(active_start: str, days: int = 90) -> str:
    """Return active_start minus `days` days as YYYY-MM-DD, for plans written before first push."""
    try:
        return (datetime.fromisoformat(active_start) - timedelta(days=days)).strftime("%Y-%m-%d")
    except Exception:
        return active_start


def _commits_for_repo(timeline: list, org: str, repo: str) -> list[dict]:
    for entry in timeline:
        if entry.get("org") == org and entry.get("repo") == repo:
            return entry.get("all_commits", [])
    return []


def _find_pai_learnings(repo: str) -> list[dict]:
    """Return PAI learning files that mention this repo name."""
    if not PAI_LEARNINGS.exists():
        return []
    hits = []
    repo_lower = repo.lower().replace("-", "").replace("_", "")
    for path in sorted(PAI_LEARNINGS.glob("*.md")):
        try:
            text = path.read_text(errors="ignore")
            # match repo name loosely (strip hyphens/underscores for comparison)
            text_stripped = text.lower().replace("-", "").replace("_", "")
            if repo_lower in text_stripped:
                # grab first meaningful content line — skip frontmatter, headers, dates
                lines = [
                    l.strip() for l in text.splitlines()
                    if l.strip()
                    and not l.startswith("#")
                    and not l.startswith("**Date")
                    and not l.startswith("date:")
                    and not re.match(r"^\*\*\d{4}", l)
                    and len(l.strip()) > 20
                ]
                summary = lines[0][:200] if lines else path.stem.replace("-", " ")
                hits.append({"file": path.name, "summary": summary, "path": str(path)})
        except Exception:
            pass
    return hits


def _git_first_commit_date(file_path: Path, git_root: Path) -> str | None:
    """
    Return the ISO date string of the first git commit that introduced this file.
    Returns None if not in git history or on error.
    """
    try:
        rel = file_path.relative_to(git_root)
        result = subprocess.run(
            ["git", "log", "--follow", "--format=%ai", "--", str(rel)],
            capture_output=True, text=True, cwd=git_root, timeout=5,
        )
        lines = result.stdout.strip().splitlines()
        if lines:
            return lines[-1][:10]  # oldest entry = first commit date, YYYY-MM-DD
    except Exception:
        pass
    return None


def _find_local_repo(repo: str) -> Path | None:
    """Find a local clone of this repo by name, searching common roots."""
    for root in _LOCAL_SEARCH_ROOTS:
        p = root / repo
        if p.is_dir() and (p / ".git").is_dir():
            return p
    return None


def _find_repo_docs(repo: str, first_commit: str, last_commit: str) -> list[dict]:
    """
    For repos that have a local clone, scan their .md files using git log to get real
    commit dates. Only returns docs committed during the repo's active period.

    Priority: DEV_MAN/plans/ > DEV_MAN/ > CLAUDE.md > changelogs > README.md

    Returns list of {filename, rel_path, first_git_date, content_preview, is_plan_doc, source}
    """
    repo_path = _find_local_repo(repo)
    if not repo_path:
        return []

    active_start = first_commit[:10] if first_commit else "2020-01-01"
    active_end = last_commit[:10] if last_commit else "2030-01-01"
    buffered_start = _buffered_start(active_start)

    hits = []
    # Scan all .md files, prioritizing plan docs
    md_files = sorted(repo_path.glob("**/*.md"))
    skip_patterns = ["node_modules", ".git", "__pycache__", "venv", ".venv"]

    for md_path in md_files:
        rel = str(md_path.relative_to(repo_path))
        if any(skip in rel for skip in skip_patterns):
            continue

        # Get real commit date via git
        first_git_date = _git_first_commit_date(md_path, repo_path)
        if not first_git_date:
            continue

        # Only include docs committed during the repo's active window
        if first_git_date > active_end:
            continue
        if first_git_date < buffered_start:
            continue

        is_plan = bool(_PLAN_SIGNALS.search(rel))
        # Read content preview — prose only, no tables/badges/frontmatter
        content_preview = ""
        try:
            raw = md_path.read_text(errors="ignore")
            lines = []
            for l in raw.splitlines():
                s = l.strip()
                if not s:
                    continue
                # skip: headers, frontmatter dividers, table rows, badge lines, date stamps
                if s.startswith("#"):
                    continue
                if re.match(r"^(\*\*Date|date:|---|\||\[!\[|!\[|_Last updated)", s):
                    continue
                if s.count("|") > 2:  # table row
                    continue
                if len(s) < 30:
                    continue
                lines.append(s)
            content_preview = " ".join(lines)[:600]
        except Exception:
            pass

        hits.append({
            "filename": md_path.name,
            "rel_path": rel,
            "first_git_date": first_git_date,
            "content_preview": content_preview,
            "is_plan_doc": is_plan,
            "source": "local_git",
        })

    # Sort priority:
    # 1. DEV_MAN/plans/ docs (most deliberate vision writing)
    # 2. Other plan-signal docs (changelog, claude, etc.)
    # 3. Everything else
    # Within each tier, earliest commit first (written during active development)
    def _sort_key(h):
        rel = h.get("rel_path", "")
        if "DEV_MAN" in rel and "plans" in rel:
            tier = 0
        elif h["is_plan_doc"]:
            tier = 1
        else:
            tier = 2
        return (tier, h["first_git_date"])

    hits.sort(key=_sort_key)
    # Return all DEV_MAN/plans/ docs, cap total at 30
    return hits[:30]


def _find_mdops_docs(repo: str, first_commit: str = "", last_commit: str = "") -> list[dict]:
    """
    Query the mdops DB for documents belonging to this repo.

    Uses docs_for_repo() which matches on git_remotes LIKE %repo% — this correctly
    finds ALL docs in a repo (not just ones whose *filename* contains the repo name).
    E.g. AGOE/DEV_MAN/Plann.v.0.0.1.md is found even though "AGOE" isn't in the filename.

    Returns docs ranked: DEV_MAN/plans/ > other plan-signal docs > rest.
    Each result: {id, title, filename, content_preview, is_plan_doc, first_git_date}
    """
    try:
        results = docs_for_repo(repo)
    except Exception:
        return []

    if not results:
        return []

    active_start = first_commit[:10] if first_commit else ""
    active_end = last_commit[:10] if last_commit else ""
    buf_start = _buffered_start(active_start) if active_start else ""

    hits = []
    for r in results:
        filename = r.get("filename", "") or ""
        title = r.get("title", "") or ""
        doc_id = r.get("id")
        full_path_str = r.get("full_path", "") or ""
        git_root_str = r.get("git_root", "") or ""
        if not doc_id:
            continue

        rel_path = r.get("relative_path", "") or ""
        is_plan = bool(_PLAN_SIGNALS.search(rel_path) or _PLAN_SIGNALS.search(filename) or _PLAN_SIGNALS.search(title))

        # Verify commit date via git log on the actual file
        first_git_date = None
        if full_path_str and git_root_str:
            fp = Path(full_path_str)
            gr = Path(git_root_str)
            if fp.exists() and gr.exists():
                first_git_date = _git_first_commit_date(fp, gr)

        # Filter: doc must have been written during the repo's active window
        if first_git_date and buf_start and active_end:
            if first_git_date < buf_start or first_git_date > active_end:
                continue

        # Pull content for plan docs (file content is read on demand from disk)
        content_preview = ""
        if is_plan and full_path_str:
            fp = Path(full_path_str)
            if fp.exists():
                try:
                    full = get_doc(doc_id)
                    raw = full.get("content", "") or ""
                    lines = [
                        l.strip() for l in raw.splitlines()
                        if l.strip() and not l.startswith("#") and len(l.strip()) > 30
                    ]
                    content_preview = " ".join(lines)[:600]
                except Exception:
                    pass

        # Sort tier: DEV_MAN/plans/ (0) > other plan-signal (1) > rest (2)
        if "DEV_MAN" in rel_path and "plan" in rel_path.lower():
            tier = 0
        elif is_plan:
            tier = 1
        else:
            tier = 2

        hits.append({
            "id": doc_id,
            "title": title,
            "filename": filename,
            "rel_path": rel_path,
            "content_preview": content_preview,
            "is_plan_doc": is_plan,
            "first_git_date": first_git_date,
            "word_count": r.get("word_count", 0) or 0,
            "tier": tier,
            "source": "mdops",
        })

    # Sort: tier asc, then word_count desc (longest doc wins within tier), then date asc
    hits.sort(key=lambda h: (h["tier"], -(h["word_count"]), h.get("first_git_date") or "z"))
    return hits


def _select_best_plan_doc(
    repo_docs: list[dict] | None,
    mdops_docs: list[dict] | None,
) -> tuple[dict | None, str | None]:
    """
    Pick the best plan/vision doc for Q4, returning (doc, source).
    Prefers local repo docs over mdops; within local, prefers high-signal titles (latest first).
    """
    if repo_docs:
        hs = [
            d for d in repo_docs
            if d["is_plan_doc"] and d.get("content_preview")
            and _HIGH_SIGNAL.search(d.get("rel_path", "") + d.get("filename", ""))
        ]
        if hs:
            return max(hs, key=lambda d: d.get("first_git_date", "")), "local"
        candidates = [d for d in repo_docs if d["is_plan_doc"] and d.get("content_preview")]
        if candidates:
            return max(candidates, key=lambda d: len(d.get("content_preview", ""))), "local"

    if mdops_docs:
        # Prefer docs with content, but accept high-tier plan docs even without content
        # (e.g. DEV_MAN/Plann.v.0.0.1.md tells us a plan existed even if file is gone)
        doc = next((d for d in mdops_docs if d["is_plan_doc"] and d.get("content_preview")), None)
        if not doc:
            doc = next((d for d in mdops_docs if d["is_plan_doc"] and d.get("tier", 2) <= 1), None)
        if doc:
            return doc, "mdops"

    return None, None


def _pick_signal_commits(commits: list[dict]) -> dict:
    """
    From the full commit list pick:
      - first:  the oldest (origin story)
      - pivot:  a commit with keywords suggesting a major change
      - last:   the most recent (where it ended up)
    """
    if not commits:
        return {}
    # commits come newest-first from GitHub API
    sorted_asc = list(reversed(commits))
    first = sorted_asc[0]
    last = sorted_asc[-1]

    pivot = None
    pivot_keywords = re.compile(
        r"\b(refactor|rewrite|rebuild|migrate|switch|replace|break|fix|feat|add|init|"
        r"overhaul|redesign|pivot|remove|delete|archive|merge|pr|deploy|ci|docker|"
        r"prod|production|launch|release|v\d|v\.|major|complete|done|finish)\b",
        re.I,
    )
    pivot_score = -1
    for c in sorted_asc[1:-1]:  # skip first and last
        msg = c.get("message", "")
        score = len(pivot_keywords.findall(msg))
        if score > pivot_score:
            pivot_score = score
            pivot = c

    return {"first": first, "pivot": pivot, "last": last if last != first else None}


def _fmt_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%B %d, %Y")
    except Exception:
        return iso[:10]


def _build_specific_questions(
    repo: str,
    org: str,
    signals: dict,
    learnings: list[dict],
    repo_row: dict,
    mdops_docs: list[dict] | None = None,
    repo_docs: list[dict] | None = None,
) -> list[dict]:
    """
    Build 5 specific questions from real data.
    Each question has: seq, question_text, question_type, data_source, data_ref
    """
    first = signals.get("first")
    pivot = signals.get("pivot")
    last = signals.get("last")
    total = repo_row.get("total_commits", 0)
    description = repo_row.get("description", "") or ""
    readme = (repo_row.get("readme_preview") or "")[:300]
    is_fork = bool(repo_row.get("is_fork"))
    chapter = repo_row.get("chapter", "")
    language = repo_row.get("language", "") or "unknown"

    # Fall back to DB-stored first/last commit when all_commits wasn't captured
    if not first and repo_row.get("first_commit_date"):
        first = {
            "date": repo_row["first_commit_date"],
            "message": repo_row.get("first_commit_msg", ""),
            "sha": repo_row.get("first_commit_sha", ""),
        }
    if not last and repo_row.get("last_commit_date"):
        last = {
            "date": repo_row["last_commit_date"],
            "message": repo_row.get("last_commit_msg", ""),
            "sha": repo_row.get("last_commit_sha", ""),
        }

    qs: list[dict] = []

    # ── Q1: ORIGIN ────────────────────────────────────────────────────────────
    if first:
        date_str = _fmt_date(first.get("date", ""))
        msg = first.get("message", "").strip()[:120]
        sha = first.get("sha", "")[:8]
        if is_fork:
            text = (
                f"On {date_str} you forked {repo}. "
                f"Your first commit was \"{msg}\" (sha: {sha}). "
                f"What were you trying to learn or use from this? Did you actually build anything on top of it?"
            )
        else:
            text = (
                f"Your first commit to {repo} on {date_str} was: \"{msg}\" (sha: {sha}). "
                f"Walk me through that moment — what were you trying to build and why did you start it?"
            )
        qs.append({"seq": 1, "question_type": "origin", "question_text": text,
                   "data_source": "gh_commit", "data_ref": sha})

    # ── Q2: TECHNICAL ─────────────────────────────────────────────────────────
    tech_context = ""
    readme_clean = re.sub(r"<[^>]+>", "", readme).strip()[:300] if readme else ""
    readme_clean = re.sub(r"\s+", " ", readme_clean).strip()
    if readme_clean and len(readme_clean) > 30:
        tech_context = f"The README says: \"{readme_clean[:200]}\". "
    elif description:
        tech_context = f"Description: \"{description}\". "

    if pivot:
        date_str = _fmt_date(pivot.get("date", ""))
        msg = pivot.get("message", "").strip()[:120]
        sha = pivot.get("sha", "")[:8]
        text = (
            f"{tech_context}"
            f"Around {date_str} you made this commit: \"{msg}\" (sha: {sha}). "
            f"That looks like a turning point. What was breaking or changing at that moment? "
            f"What did you figure out?"
        )
        qs.append({"seq": 2, "question_type": "technical", "question_text": text,
                   "data_source": "gh_commit", "data_ref": sha})
    else:
        text = (
            f"{tech_context}"
            f"This repo has {total} commits in {language}. "
            f"What was the hardest technical problem you ran into here?"
        )
        qs.append({"seq": 2, "question_type": "technical", "question_text": text,
                   "data_source": "gh_repo", "data_ref": f"{org}/{repo}"})

    # ── Q3: PAI LEARNING or FAILURE ───────────────────────────────────────────
    if learnings:
        l = learnings[0]
        text = (
            f"There's a learning you documented: \"{l['summary'][:200]}\". "
            f"That came from working on {repo}. What happened — walk me through the failure or discovery."
        )
        qs.append({"seq": 3, "question_type": "failure", "question_text": text,
                   "data_source": "pai_learning", "data_ref": l["file"]})
    elif total > 1:
        end_msg = (last.get("message", "").strip()[:100] if last else "")
        if end_msg:
            text = (
                f"Your last commit to this project was: \"{end_msg}\". "
                f"Did you consider this done? What stopped you — or is it still alive?"
            )
        else:
            text = (
                f"{repo} has {total} commits. Did you ever feel like you failed at what you were trying to do here? "
                f"What would a version 2 have looked like?"
            )
        qs.append({"seq": 3, "question_type": "failure", "question_text": text,
                   "data_source": "gh_commit", "data_ref": last.get("sha", "")[:8] if last else ""})
    else:
        qs.append({"seq": 3, "question_type": "failure",
                   "question_text": f"What did {repo} teach you that you used somewhere else?",
                   "data_source": "manual", "data_ref": ""})

    # ── Q4: VISION vs REALITY (from mdops plan docs when available) ──────────
    chapter_map = {
        "collecting_era": "You were collecting tools in 2023, before you knew what you'd build.",
        "learning_era": "You were following other people's tutorials and frameworks.",
        "building_era": "You started building things for your actual business.",
        "going_all_in": "You went all in — 2025, Pete-DB, PAI, Terry starting to take shape.",
        "infrastructure_era": "The infrastructure era — systems talking to systems, Terry running autonomously.",
    }
    era_context = chapter_map.get(chapter, "")

    plan_doc, plan_source = _select_best_plan_doc(repo_docs, mdops_docs)

    if plan_doc:
        preview = plan_doc.get("content_preview", "")[:400]
        doc_name = plan_doc.get("filename", plan_doc.get("title", ""))
        date_ctx = f" (committed {plan_doc['first_git_date']})" if plan_doc.get("first_git_date") else ""

        if preview:
            # We have actual content to quote
            text = (
                f"There's a document called \"{doc_name}\"{date_ctx} from the {repo} repo. "
                f"It says: \"{preview}\". "
                f"That was written while you were actively building this. "
                f"How much of that plan actually shipped? Where did reality diverge?"
            )
        else:
            # File is gone (stale mdops path) but we know the doc existed — use the name as evidence
            rel = plan_doc.get("rel_path", "") or plan_doc.get("filename", doc_name)
            text = (
                f"You wrote a planning document called \"{doc_name}\" in {repo} ({rel}){date_ctx}. "
                f"I can see it existed but the file isn't on disk anymore. "
                f"What was in that document — what were you planning, and did any of it ship?"
            )

        data_ref = plan_doc.get("rel_path", "") or str(plan_doc.get("id", ""))
        qs.append({"seq": 4, "question_type": "vision", "question_text": text,
                   "data_source": f"repo_doc_{plan_source}", "data_ref": data_ref})
    else:
        text = (
            f"{era_context} "
            f"What was your MCV — Mark Carpenter Vision — for {repo}? "
            f"In one sentence: what did you want this to become, and how close did you get?"
        )
        qs.append({"seq": 4, "question_type": "vision", "question_text": text.strip(),
                   "data_source": "manual", "data_ref": ""})

    # ── Q5: PERSONAL / IDENTITY ───────────────────────────────────────────────
    if chapter == "collecting_era":
        text = (
            f"When you created {repo} you probably didn't call yourself a developer. "
            f"What did you call yourself? What was your mental model of what you were doing?"
        )
    elif chapter == "learning_era":
        text = (
            f"At the time of {repo} you were mostly copying other people's code. "
            f"When did that shift — when did you start feeling like you were writing your own thing?"
        )
    elif total > 100:
        text = (
            f"{repo} has {total} commits — you stayed with this one. "
            f"Why? What kept you coming back to it when other things got abandoned?"
        )
    elif is_fork:
        text = (
            f"You forked {repo} but didn't build much on it. "
            f"What were you hoping to understand or steal from it?"
        )
    else:
        text = (
            f"If you showed {repo} to yourself from two years ago — the person who didn't know what GitHub was — "
            f"what would that version of you think?"
        )
    qs.append({"seq": 5, "question_type": "personal", "question_text": text,
               "data_source": "manual", "data_ref": ""})

    return qs


_EPISODE_QUERY = """
    SELECT e.id as episode_id, e.repo_id,
           r.org, r.repo, r.total_commits, r.is_fork,
           r.description, r.readme_preview, r.language, r.chapter,
           r.first_commit_date, r.first_commit_msg
    FROM journey_episodes e
    JOIN journey_repos r ON r.id = e.repo_id
"""


def _enrich_row(row: dict, timeline: list) -> tuple[list[dict], dict]:
    """
    Run the full enrichment pipeline for one row and write questions to DB.
    Returns (questions, stats) where stats has learnings/docs/commits counts.
    """
    repo = row["repo"]
    org = row["org"]
    first_commit = row.get("first_commit_date", "") or ""
    commits = _commits_for_repo(timeline, org, repo)
    last_commit = commits[0].get("date", "") if commits else ""

    signals = _pick_signal_commits(commits)
    learnings = _find_pai_learnings(repo)
    repo_docs = _find_repo_docs(repo, first_commit, last_commit)
    mdops_docs = _find_mdops_docs(repo, first_commit, last_commit)
    questions = _build_specific_questions(repo, org, signals, learnings, row, mdops_docs, repo_docs)

    episode_id = row["episode_id"]
    with _conn() as conn:
        # Only replace non-edited questions — preserve human edits (is_edited=1)
        conn.execute(
            "DELETE FROM journey_questions WHERE episode_id=? AND persona='default' AND is_edited=0",
            (episode_id,),
        )
        # Re-insert only questions that weren't already edited by the user
        existing_edited_seqs = {
            r[0] for r in conn.execute(
                "SELECT seq FROM journey_questions WHERE episode_id=? AND persona='default' AND is_edited=1",
                (episode_id,),
            ).fetchall()
        }
        to_insert = [q for q in questions if q["seq"] not in existing_edited_seqs]
        conn.executemany(
            """INSERT INTO journey_questions
               (episode_id, seq, question_text, question_type, data_source, data_ref, persona, is_edited)
               VALUES (?,?,?,?,?,?,'default',0)""",
            [(episode_id, q["seq"], q["question_text"], q["question_type"],
              q["data_source"], q["data_ref"]) for q in to_insert],
        )

    stats = {
        "learnings_found": len(learnings),
        "repo_docs_found": len(repo_docs),
        "repo_plan_docs_found": sum(1 for d in repo_docs if d["is_plan_doc"]),
        "mdops_docs_found": len(mdops_docs),
        "plan_docs_found": sum(1 for d in mdops_docs if d["is_plan_doc"]),
        "commits_found": len(commits),
    }
    return questions, stats


# ── public enrichment functions ───────────────────────────────────────────────

def enrich_all_episodes(limit: int | None = None) -> dict:
    """
    Enrich every repo episode with specific questions from real commit data.
    Returns counts: {enriched, skipped, errors}
    """
    init_db()
    logger.info("Loading journey_v1.json …")
    timeline = _load_json().get("timeline", [])
    logger.info(f"Scanning PAI learnings at {PAI_LEARNINGS} …")

    with _conn() as conn:
        rows = conn.execute(_EPISODE_QUERY + " ORDER BY r.first_commit_date").fetchall()

    rows = [dict(r) for r in rows]
    if limit:
        rows = rows[:limit]

    enriched = skipped = errors = 0
    for row in rows:
        try:
            _enrich_row(row, timeline)
            enriched += 1
        except Exception as e:
            logger.error(f"Error enriching episode {row.get('episode_id')} ({row.get('repo')}): {e}")
            errors += 1

    logger.info(f"Enrichment done — enriched={enriched} skipped={skipped} errors={errors}")
    return {"enriched": enriched, "skipped": skipped, "errors": errors}


def enrich_one_episode(episode_id: int) -> dict:
    """Enrich a single episode — called from the UI when you click 'Deep Dive'."""
    init_db()
    timeline = _load_json().get("timeline", [])

    with _conn() as conn:
        row = conn.execute(
            _EPISODE_QUERY + " WHERE e.id = ?", (episode_id,)
        ).fetchone()

    if not row:
        return {"error": "episode not found"}

    row = dict(row)
    questions, stats = _enrich_row(row, timeline)

    return {"episode_id": episode_id, "repo": row["repo"], "questions": questions, **stats}
