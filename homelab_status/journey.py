"""
Journey — Mark Carpenter's GitHub story layer.

Three concerns:
  1. Import raw data from journey_v1.json into journey_repos + journey_chapters
  2. Scaffold interview episodes + questions from that data
  3. Query functions for the API layer

Data flows ONE WAY:
  journey_v1.json (source) → journey_repos (facts) → journey_episodes → journey_questions (stories)

Never delete from journey_repos — it's the immutable journalist archive.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from .db import _conn, init_db

JOURNEY_JSON = Path(__file__).parent.parent / "data" / "journey_v1.json"

CHAPTER_TITLES = {
    "collecting_era":     "The Collecting Era",
    "learning_era":       "The Learning Era",
    "building_era":       "The Building Era",
    "going_all_in":       "Going All In",
    "infrastructure_era": "The Infrastructure Era",
}

CHAPTER_NARRATIVES = {
    "collecting_era": (
        "Mark discovered AI in August 2023. He didn't build — he collected. "
        "Sixteen repos forked from Auto-GPT, LangFlow, Flowise, Superagent. "
        "He was trying to understand what was possible before he knew what he wanted to build."
    ),
    "learning_era": (
        "CrewAI, groq tutorials, EmailAutomation. Mark was following frameworks, "
        "copying patterns, running other people's code. The real estate thread "
        "was always there underneath — he just hadn't found the angle yet."
    ),
    "building_era": (
        "July 2024: the first tools built for Mark's actual business. "
        "call-center-ops, Fabric-wrksp, real estate data tools. "
        "Forty-two repos — the most prolific period. He was building to solve "
        "problems he had today, not hypothetical future ones."
    ),
    "going_all_in": (
        "All of 2025. Pete-DB (214 commits), PAI (79 commits), aivoiceagents, "
        "completed-interviews — an attempt at this exact interview system, one year earlier. "
        "Terry's embryo appears. The infrastructure thinking begins."
    ),
    "infrastructure_era": (
        "January 2026 onward. 00Myhomelab accumulates 1,519 commits. "
        "Terry runs autonomously. homelab-status is built to make sense of everything. "
        "The tools now talk to each other. The system is alive."
    ),
}

# Opening hook questions per chapter — what the AI interviewer asks first
CHAPTER_HOOKS = {
    "collecting_era":     "You made your first GitHub commit on August 1st, 2023 — a file called 'Read Me.txt'. What were you actually trying to do that day?",
    "learning_era":       "You spent six months running other people's code. What were you actually looking for?",
    "building_era":       "July 2024 — you stopped forking and started building. What changed?",
    "going_all_in":       "2025 — 59 repos in one year. Was that focus or chaos?",
    "infrastructure_era": "Your homelab now has 1,519 commits and runs autonomously. Three years ago you didn't know what GitHub was. How do you make sense of that?",
}

# Question templates by type
QUESTION_TEMPLATES = {
    "origin": [
        "What problem were you trying to solve when you started {repo}?",
        "Walk me through your thinking the day you created {repo}.",
        "What did you think this was going to become?",
    ],
    "pivot": [
        "You went from {prev_repo} to {repo} in {days} days. What happened?",
        "There's a gap of {gap} between your last commit here and your next repo. What were you doing?",
        "Why did you stop working on {repo}?",
    ],
    "failure": [
        "This repo has {commits} commits and is never mentioned in your homelab. What happened to it?",
        "You tried to build a voice interview system in May 2025 — completed-interviews — and it never got past the initial commit. What stopped you?",
        "There are {open_issues} open issues here. Did you run out of time or did you hit a wall?",
    ],
    "vision": [
        "What was the MCV — Mark Carpenter Vision — for {repo}?",
        "If this had worked exactly as you imagined, what would it look like today?",
        "How close did you get?",
    ],
    "technical": [
        "You were using {language} at this point. Why that choice?",
        "This was your first repo with Docker. What made you learn that?",
        "Walk me through what this code actually does — explain it like I'm not a developer.",
    ],
    "personal": [
        "At this point in the journey, did you think of yourself as a developer?",
        "Were you scared to show people this code?",
        "Who did you tell about this when you built it?",
    ],
}


# ── Import ────────────────────────────────────────────────────────────────────

def import_journey_json(path: Path = JOURNEY_JSON) -> dict:
    """Seed journey_repos and journey_chapters from journey_v1.json. Idempotent."""
    init_db()
    if not path.exists():
        return {"error": f"journey_v1.json not found at {path}"}

    with open(path) as f:
        data = json.load(f)

    ts = datetime.now(timezone.utc).isoformat()
    chapters = data.get("chapters", {})
    timeline = data.get("timeline", [])

    repos_inserted = 0
    repos_skipped = 0

    with _conn() as conn:
        # 1. Upsert chapters
        for name, ch in chapters.items():
            conn.execute(
                """INSERT INTO journey_chapters (name, title, start_date, end_date, narrative, created_at)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(name) DO UPDATE SET
                     title=excluded.title,
                     start_date=excluded.start_date,
                     end_date=excluded.end_date,
                     narrative=excluded.narrative""",
                (
                    name,
                    CHAPTER_TITLES.get(name, name),
                    ch.get("start", ""),
                    ch.get("end", ""),
                    CHAPTER_NARRATIVES.get(name, ""),
                    ts,
                ),
            )

        # 2. Upsert repos — one row per org/repo
        # Assign chapter by created_at date falling within chapter date ranges
        chapter_ranges = []
        for ch_name, ch_data in chapters.items():
            start = ch_data.get("start", "")  # e.g. "2023-08"
            end = ch_data.get("end", "")       # e.g. "2023-12"
            chapter_ranges.append((ch_name, start, end))

        def _assign_chapter(created_at: str) -> str:
            if not created_at:
                return ""
            date_prefix = created_at[:7]  # "YYYY-MM"
            for ch_name, start, end in chapter_ranges:
                if start <= date_prefix <= end:
                    return ch_name
            return ""

        for entry in timeline:
            repo = entry.get("repo", "")
            org = entry.get("org", "")
            if not repo or not org:
                continue

            fc = entry.get("first_commit") or {}
            lc = entry.get("last_commit") or {}
            chapter = _assign_chapter(entry.get("created_at", ""))

            try:
                conn.execute(
                    """INSERT INTO journey_repos
                       (org, repo, created_at, description, is_fork, language, topics,
                        total_commits, first_commit_date, first_commit_msg, first_commit_sha,
                        last_commit_date, last_commit_msg, readme_preview,
                        has_docker, has_tests, has_ci, has_claude_md,
                        chapter, notes, imported_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(org, repo) DO UPDATE SET
                         description=excluded.description,
                         total_commits=excluded.total_commits,
                         last_commit_date=excluded.last_commit_date,
                         last_commit_msg=excluded.last_commit_msg,
                         chapter=excluded.chapter,
                         notes=excluded.notes,
                         imported_at=excluded.imported_at""",
                    (
                        org, repo,
                        entry.get("created_at", ""),
                        entry.get("description", "") or "",
                        int(entry.get("is_fork", False)),
                        entry.get("language", "") or "",
                        json.dumps(entry.get("topics", []) or []),
                        entry.get("total_commits", 0) or 0,
                        fc.get("date", "") or "",
                        fc.get("message", "") or "",
                        fc.get("sha", "") or "",
                        lc.get("date", "") or "",
                        lc.get("message", "") or "",
                        (entry.get("readme_preview", "") or "")[:1000],
                        int(entry.get("has_docker", False)),
                        int(entry.get("has_tests", False)),
                        int(entry.get("has_ci", False)),
                        int(entry.get("has_claude_md", False)),
                        chapter,
                        entry.get("notes", "") or "",
                        ts,
                    ),
                )
                repos_inserted += 1
            except Exception as e:
                logger.warning(f"Skipped {org}/{repo}: {e}")
                repos_skipped += 1

    logger.info(f"Journey import: {repos_inserted} repos upserted, {repos_skipped} skipped")
    return {"repos_inserted": repos_inserted, "repos_skipped": repos_skipped, "chapters": len(chapters)}


# ── Episode scaffolding ───────────────────────────────────────────────────────

def scaffold_episodes() -> dict:
    """
    Auto-create draft episodes for every chapter + notable repos.
    Safe to run multiple times — skips existing episodes for the same repo.
    """
    init_db()
    ts = datetime.now(timezone.utc).isoformat()
    created = 0

    with _conn() as conn:
        chapters = {
            row["name"]: row["id"]
            for row in conn.execute("SELECT id, name FROM journey_chapters").fetchall()
        }

        # One episode per chapter (the "era overview" episode)
        for ch_name, ch_id in chapters.items():
            exists = conn.execute(
                "SELECT id FROM journey_episodes WHERE chapter_id=? AND repo_id IS NULL",
                (ch_id,),
            ).fetchone()
            if not exists:
                conn.execute(
                    """INSERT INTO journey_episodes
                       (chapter_id, repo_id, title, hook, status, created_at)
                       VALUES (?,?,?,?,?,?)""",
                    (
                        ch_id, None,
                        f"Chapter: {CHAPTER_TITLES.get(ch_name, ch_name)}",
                        CHAPTER_HOOKS.get(ch_name, ""),
                        "draft", ts,
                    ),
                )
                created += 1

        # Individual episodes for repos with enough substance
        repos = conn.execute(
            """SELECT id, org, repo, chapter, description, total_commits,
                      first_commit_date, first_commit_msg, language, is_fork
               FROM journey_repos
               WHERE total_commits > 1 OR is_fork = 0
               ORDER BY first_commit_date""",
        ).fetchall()

        for i, row in enumerate(repos, 1):
            ch_id = chapters.get(row["chapter"])
            exists = conn.execute(
                "SELECT id FROM journey_episodes WHERE repo_id=?", (row["id"],)
            ).fetchone()
            if exists:
                continue

            fork_note = " (you forked this)" if row["is_fork"] else ""
            title = f"Ep {i}: {row['org']}/{row['repo']}{fork_note}"
            hook = (
                f"Your first commit to {row['repo']} was on "
                f"{(row['first_commit_date'] or '')[:10]} — "
                f"\"{(row['first_commit_msg'] or 'no message')[:80]}\". "
                f"What were you thinking?"
            )

            cur = conn.execute(
                """INSERT INTO journey_episodes
                   (chapter_id, repo_id, episode_num, title, hook, status, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (ch_id, row["id"], i, title, hook, "draft", ts),
            )
            ep_id = cur.lastrowid
            created += 1

            # Seed 3-5 questions per episode
            _seed_questions(conn, ep_id, dict(row), ts)

    return {"episodes_created": created}


def _seed_questions(conn, episode_id: int, repo: dict, ts: str) -> None:
    """Insert starter questions for one episode based on repo data."""
    questions = []

    # Always start with origin
    questions.append((
        1, f"What problem were you trying to solve when you started {repo['repo']}?",
        "origin", "gh_repo", f"{repo['org']}/{repo['repo']}",
    ))

    # First commit question
    if repo.get("first_commit_msg"):
        questions.append((
            2, f"Your first commit message was: \"{repo['first_commit_msg'][:120]}\". "
               f"Explain that to me like I'm not a developer.",
            "technical", "gh_commit", repo.get("first_commit_sha", ""),
        ))

    # Fork question
    if repo.get("is_fork"):
        questions.append((
            3, f"You forked {repo['repo']} — you didn't build it, you borrowed it. "
               f"What were you actually trying to learn from it?",
            "personal", "gh_repo", f"{repo['org']}/{repo['repo']}",
        ))
    else:
        questions.append((
            3, f"What was your MCV — your Mark Carpenter Vision — for {repo['repo']}? "
               f"What did you want it to become?",
            "vision", "gh_repo", f"{repo['org']}/{repo['repo']}",
        ))

    # Failure / completion question
    questions.append((
        4, f"Looking at this now — {repo.get('total_commits', 0)} commits, "
           f"last touched {(repo.get('last_commit_date') or '')[:10]} — "
           f"how close did you get to what you imagined?",
        "failure", "gh_repo", f"{repo['org']}/{repo['repo']}",
    ))

    # Personal closing
    questions.append((
        5, "At the time you built this, did you think of yourself as a developer?",
        "personal", "manual", "",
    ))

    conn.executemany(
        """INSERT INTO journey_questions
           (episode_id, seq, question_text, question_type, data_source, data_ref)
           VALUES (?,?,?,?,?,?)""",
        [(episode_id, seq, text, qtype, source, ref)
         for seq, text, qtype, source, ref in questions],
    )


# ── Query functions ───────────────────────────────────────────────────────────

def get_chapters() -> list[dict]:
    init_db()
    with _conn() as conn:
        rows = conn.execute(
            """SELECT c.*, COUNT(e.id) as episode_count
               FROM journey_chapters c
               LEFT JOIN journey_episodes e ON e.chapter_id = c.id
               GROUP BY c.id
               ORDER BY c.start_date"""
        ).fetchall()
    return [dict(r) for r in rows]


def get_episodes(chapter_name: str | None = None, status: str | None = None) -> list[dict]:
    init_db()
    with _conn() as conn:
        where = []
        params: list = []
        if chapter_name:
            where.append("c.name = ?")
            params.append(chapter_name)
        if status:
            where.append("e.status = ?")
            params.append(status)
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        rows = conn.execute(
            f"""SELECT e.*, c.name as chapter_name, c.title as chapter_title,
                       r.repo, r.org, r.language, r.total_commits, r.is_fork,
                       r.first_commit_date, r.description as repo_description
                FROM journey_episodes e
                LEFT JOIN journey_chapters c ON c.id = e.chapter_id
                LEFT JOIN journey_repos r ON r.id = e.repo_id
                {clause}
                ORDER BY r.first_commit_date, e.episode_num""",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def get_episode_questions(episode_id: int) -> list[dict]:
    init_db()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM journey_questions WHERE episode_id=? ORDER BY seq",
            (episode_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_journey_stats() -> dict:
    init_db()
    with _conn() as conn:
        repos = conn.execute("SELECT COUNT(*) as n FROM journey_repos").fetchone()["n"]
        chapters = conn.execute("SELECT COUNT(*) as n FROM journey_chapters").fetchone()["n"]
        episodes = conn.execute("SELECT COUNT(*) as n FROM journey_episodes").fetchone()["n"]
        by_status = {
            row["status"]: row["n"]
            for row in conn.execute(
                "SELECT status, COUNT(*) as n FROM journey_episodes GROUP BY status"
            ).fetchall()
        }
        date_range = conn.execute(
            "SELECT MIN(first_commit_date) as first, MAX(last_commit_date) as last FROM journey_repos"
        ).fetchone()
    return {
        "total_repos": repos,
        "total_chapters": chapters,
        "total_episodes": episodes,
        "episodes_by_status": by_status,
        "first_commit": (date_range["first"] or "")[:10],
        "last_commit": (date_range["last"] or "")[:10],
    }


def update_episode(episode_id: int, **fields) -> bool:
    """Update episode fields — used when marking recorded, adding transcript, etc."""
    init_db()
    allowed = {"status", "title", "hook", "recorded_at", "published_at", "audio_url", "transcript"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    with _conn() as conn:
        set_clause = ", ".join(f"{k}=?" for k in updates)
        conn.execute(
            f"UPDATE journey_episodes SET {set_clause} WHERE id=?",
            list(updates.values()) + [episode_id],
        )
    return True


def save_answer(question_id: int, answer_text: str) -> bool:
    """Save Mark's answer to a question after an interview session."""
    init_db()
    ts = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        conn.execute(
            "UPDATE journey_questions SET answer_text=?, recorded_at=? WHERE id=?",
            (answer_text, ts, question_id),
        )
    return True
