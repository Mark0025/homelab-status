"""
Deep enrichment — replaces generic template questions with specific ones.

For each repo episode:
  1. Load commit history from journey_v1.json (already captured)
  2. Scan PAI learnings for any that mention this repo
  3. Pick 3 signal commits: first, biggest pivot, last
  4. Rewrite questions with real dates, real commit messages, real context

This is idempotent — run it again and it overwrites questions.
It never touches journey_repos (the immutable archive).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from .db import _conn, init_db

JOURNEY_JSON = Path(__file__).parent.parent / "data" / "journey_v1.json"
PAI_LEARNINGS = Path.home() / ".claude" / "context" / "learnings"

# ── helpers ──────────────────────────────────────────────────────────────────

def _load_json() -> dict:
    with open(JOURNEY_JSON) as f:
        return json.load(f)


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

    # ── Q4: VISION ────────────────────────────────────────────────────────────
    chapter_map = {
        "collecting_era": "You were collecting tools in 2023, before you knew what you'd build.",
        "learning_era": "You were following other people's tutorials and frameworks.",
        "building_era": "You started building things for your actual business.",
        "going_all_in": "You went all in — 2025, Pete-DB, PAI, Terry starting to take shape.",
        "infrastructure_era": "The infrastructure era — systems talking to systems, Terry running autonomously.",
    }
    era_context = chapter_map.get(chapter, "")

    text = (
        f"{era_context} "
        f"What was your MCV — Mark Carpenter Vision — for {repo}? "
        f"In one sentence: what did you want this to become?"
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


# ── main enrichment function ──────────────────────────────────────────────────

def enrich_all_episodes(limit: int | None = None) -> dict:
    """
    Enrich every repo episode with specific questions from real commit data.
    Returns counts: {enriched, skipped, errors}
    """
    init_db()
    logger.info("Loading journey_v1.json …")
    data = _load_json()
    timeline = data.get("timeline", [])

    logger.info(f"Scanning PAI learnings at {PAI_LEARNINGS} …")

    with _conn() as conn:
        # Get all repo episodes (exclude chapter overview episodes which have no repo_id)
        rows = conn.execute("""
            SELECT e.id as episode_id, e.repo_id,
                   r.org, r.repo, r.total_commits, r.is_fork,
                   r.description, r.readme_preview, r.language, r.chapter,
                   r.first_commit_date, r.first_commit_msg
            FROM journey_episodes e
            JOIN journey_repos r ON r.id = e.repo_id
            ORDER BY r.first_commit_date
        """).fetchall()

    rows = [dict(r) for r in rows]
    if limit:
        rows = rows[:limit]

    enriched = skipped = errors = 0
    ts = datetime.now().isoformat()

    for row in rows:
        try:
            episode_id = row["episode_id"]
            org = row["org"]
            repo = row["repo"]

            commits = _commits_for_repo(timeline, org, repo)
            signals = _pick_signal_commits(commits)
            learnings = _find_pai_learnings(repo)
            questions = _build_specific_questions(repo, org, signals, learnings, row)

            with _conn() as conn:
                # Replace existing questions for this episode
                conn.execute("DELETE FROM journey_questions WHERE episode_id=?", (episode_id,))
                conn.executemany(
                    """INSERT INTO journey_questions
                       (episode_id, seq, question_text, question_type, data_source, data_ref)
                       VALUES (?,?,?,?,?,?)""",
                    [(episode_id, q["seq"], q["question_text"], q["question_type"],
                      q["data_source"], q["data_ref"]) for q in questions],
                )
            enriched += 1

        except Exception as e:
            logger.error(f"Error enriching episode {row.get('episode_id')} ({row.get('repo')}): {e}")
            errors += 1

    logger.info(f"Enrichment done — enriched={enriched} skipped={skipped} errors={errors}")
    return {"enriched": enriched, "skipped": skipped, "errors": errors}


def enrich_one_episode(episode_id: int) -> dict:
    """Enrich a single episode — called from the UI when you click 'Deep Dive'."""
    init_db()
    data = _load_json()
    timeline = data.get("timeline", [])

    with _conn() as conn:
        row = conn.execute("""
            SELECT e.id as episode_id, e.repo_id,
                   r.org, r.repo, r.total_commits, r.is_fork,
                   r.description, r.readme_preview, r.language, r.chapter,
                   r.first_commit_date, r.first_commit_msg
            FROM journey_episodes e
            JOIN journey_repos r ON r.id = e.repo_id
            WHERE e.id = ?
        """, (episode_id,)).fetchone()

    if not row:
        return {"error": "episode not found"}

    row = dict(row)
    commits = _commits_for_repo(timeline, row["org"], row["repo"])
    signals = _pick_signal_commits(commits)
    learnings = _find_pai_learnings(row["repo"])
    questions = _build_specific_questions(row["repo"], row["org"], signals, learnings, row)

    ts = datetime.now().isoformat()
    with _conn() as conn:
        conn.execute("DELETE FROM journey_questions WHERE episode_id=?", (episode_id,))
        conn.executemany(
            """INSERT INTO journey_questions
               (episode_id, seq, question_text, question_type, data_source, data_ref)
               VALUES (?,?,?,?,?,?)""",
            [(episode_id, q["seq"], q["question_text"], q["question_type"],
              q["data_source"], q["data_ref"]) for q in questions],
        )

    return {
        "episode_id": episode_id,
        "repo": row["repo"],
        "questions": questions,
        "learnings_found": len(learnings),
        "commits_found": len(commits),
    }
