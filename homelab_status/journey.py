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

# Default ElevenLabs voice for the interviewer (overridable per persona below).
DEFAULT_INTERVIEWER_VOICE_ID = "JnLbZVB3BDIX9KH4Bc1H"


def load_env_key(key_name: str) -> str:
    """Read a key from the environment, falling back to the project-root .env file."""
    import os

    val = os.environ.get(key_name, "")
    if val:
        return val
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{key_name}="):
                v = line.split("=", 1)[1].strip()
                if v:
                    return v
    return ""

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
        where = ["e.repo_id IS NOT NULL"]   # exclude chapter-placeholder episodes
        params: list = []
        if chapter_name:
            where.append("c.name = ?")
            params.append(chapter_name)
        if status:
            where.append("e.status = ?")
            params.append(status)
        clause = "WHERE " + " AND ".join(where)
        rows = conn.execute(
            f"""SELECT e.*, c.name as chapter_name, c.title as chapter_title,
                       r.repo, r.org, r.language, r.total_commits, r.is_fork,
                       r.first_commit_date, r.description as repo_description,
                       (SELECT COUNT(*) FROM journey_questions q WHERE q.episode_id = e.id) as question_count
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
        questions = conn.execute("SELECT COUNT(*) as n FROM journey_questions").fetchone()["n"]
        answered = conn.execute("SELECT COUNT(*) as n FROM journey_questions WHERE answer_text IS NOT NULL AND answer_text != ''").fetchone()["n"]
    return {
        "total_repos": repos,
        "total_chapters": chapters,
        "total_episodes": episodes,
        "total_questions": questions,
        "answered_questions": answered,
        "recorded_episodes": by_status.get("recorded", 0),
        "published_episodes": by_status.get("published", 0),
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


def update_question(question_id: int, question_text: str) -> bool:
    """Edit a question's text and mark it as human-edited so enricher won't overwrite it."""
    init_db()
    ts = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        conn.execute(
            "UPDATE journey_questions SET question_text=?, is_edited=1, edited_at=? WHERE id=?",
            (question_text, ts, question_id),
        )
    return True


def get_personas(episode_id: int) -> list[str]:
    """Return all persona names that have questions for this episode."""
    init_db()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT persona FROM journey_questions WHERE episode_id=? ORDER BY persona",
            (episode_id,),
        ).fetchall()
    return [r["persona"] for r in rows]


def clone_questions_for_persona(episode_id: int, new_persona: str) -> int:
    """
    Copy the 'default' questions for an episode under a new persona name.
    Copies start as is_edited=0 — customize them from there.
    Returns count of questions cloned, 0 if persona already exists.
    """
    init_db()
    with _conn() as conn:
        existing = conn.execute(
            "SELECT COUNT(*) FROM journey_questions WHERE episode_id=? AND persona=?",
            (episode_id, new_persona),
        ).fetchone()[0]
        if existing:
            return 0

        rows = conn.execute(
            """SELECT seq, question_text, question_type, data_source, data_ref
               FROM journey_questions WHERE episode_id=? AND persona='default' ORDER BY seq""",
            (episode_id,),
        ).fetchall()

        conn.executemany(
            """INSERT INTO journey_questions
               (episode_id, seq, question_text, question_type, data_source, data_ref, persona, is_edited)
               VALUES (?,?,?,?,?,?,?,0)""",
            [(episode_id, r["seq"], r["question_text"], r["question_type"],
              r["data_source"], r["data_ref"], new_persona) for r in rows],
        )
    return len(rows)


def get_episode_questions(episode_id: int, persona: str = "default") -> list[dict]:
    """Return questions for an episode, filtered by persona."""
    init_db()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM journey_questions WHERE episode_id=? AND persona=? ORDER BY seq",
            (episode_id, persona),
        ).fetchall()
        if not rows and persona != "default":
            rows = conn.execute(
                "SELECT * FROM journey_questions WHERE episode_id=? AND persona='default' ORDER BY seq",
                (episode_id,),
            ).fetchall()
    return [dict(r) for r in rows]


def scan_repo_deps(repo_name: str) -> dict:
    """
    Scan local clone of a repo for npm/pyproject/requirements package files.
    Returns {npm:[...], pyproject:[...], requirements:[...], has_uv: bool}
    """
    import json as _json
    import re

    search_roots = [
        Path.home(),                                # repos living directly in ~
        Path.home() / "dev",                        # ~/dev/homelab-status etc.
        Path.home() / "Desktop" / "git-projects",
        Path.home() / "Desktop" / "pete",
        Path.home() / "WebstormProjects",
        Path.home() / "Desktop",
    ]

    repo_path = None
    for root in search_roots:
        p = root / repo_name
        if p.is_dir() and (p / ".git").is_dir():
            repo_path = p
            break

    if not repo_path:
        return {}

    result: dict = {}

    pkg_json = repo_path / "package.json"
    if pkg_json.exists():
        try:
            pkg = _json.loads(pkg_json.read_text())
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            result["npm"] = sorted(deps.keys())[:30]
        except Exception:
            result["npm"] = []

    pyproject = repo_path / "pyproject.toml"
    if pyproject.exists():
        try:
            text = pyproject.read_text()
            pkgs: list[str] = []
            in_deps = False
            for line in text.splitlines():
                stripped = line.strip()
                # enter a dependencies list section
                if re.match(r'^(dependencies|dev|extras)\s*=\s*\[', stripped):
                    in_deps = True
                    continue
                if in_deps:
                    if stripped.startswith(']'):
                        in_deps = False
                        continue
                    # extract bare package name from quoted dep string
                    m = re.match(r'''["']([a-zA-Z][a-zA-Z0-9_-]+)''', stripped)
                    if m:
                        pkgs.append(m.group(1).lower().replace('-', '_'))
            result["pyproject"] = sorted(set(pkgs))[:30]
        except Exception:
            result["pyproject"] = []

    req = repo_path / "requirements.txt"
    if req.exists():
        try:
            lines = req.read_text().splitlines()
            pkgs = [re.split(r'[>=<!\[#]', l.strip())[0].strip() for l in lines if l.strip() and not l.startswith('#')]
            result["requirements"] = [p for p in pkgs if p][:30]
        except Exception:
            result["requirements"] = []

    result["has_uv"] = (repo_path / "uv.lock").exists()
    return result


def refresh_all_deps() -> dict:
    """Scan all locally cloned repos and persist their deps_snapshot."""
    init_db()
    import json as _json
    updated = 0
    with _conn() as conn:
        repos = conn.execute("SELECT id, repo FROM journey_repos").fetchall()
        for row in repos:
            deps = scan_repo_deps(row["repo"])
            if deps:
                conn.execute(
                    "UPDATE journey_repos SET deps_snapshot=? WHERE id=?",
                    (_json.dumps(deps), row["id"]),
                )
                updated += 1
    return {"updated": updated}


# Each persona carries an interview "style" (used to generate questions) and an
# ElevenLabs "voice_id" (used to voice the interviewer during playback).
PERSONA_STYLES = {
    "gary_vee": {
        "style": (
            "Gary Vaynerchuk (Gary Vee) interview style. "
            "Short, punchy, direct questions. "
            "Heavy on hustle, accountability, self-awareness. "
            "Calls out BS gently. Uses 'bro', 'look', 'the truth is', 'let me ask you something'. "
            "Pushes on whether the person is being honest with themselves. "
            "No fluff — gets to the real human behind the tech."
        ),
        "voice_id": DEFAULT_INTERVIEWER_VOICE_ID,
    },
    "lex_fridman": {
        "style": (
            "Lex Fridman interview style. "
            "Long-form, philosophical, curious. "
            "Asks about consciousness, meaning, first principles. "
            "Respectful, slow-paced, often rephrases the question more deeply. "
            "Finds the big idea inside a technical detail."
        ),
        "voice_id": DEFAULT_INTERVIEWER_VOICE_ID,
    },
    "tim_ferriss": {
        "style": (
            "Tim Ferriss interview style. "
            "Tactical, process-oriented, deconstruction. "
            "Asks 'what does your morning routine look like?', 'what was the decision that changed everything?'. "
            "Pushes on failures and what was learned. "
            "Numbers and specifics — not feelings."
        ),
        "voice_id": DEFAULT_INTERVIEWER_VOICE_ID,
    },
}


def persona_style(persona_name: str) -> str:
    """Return the interview-style prompt for a persona, or a sensible default."""
    entry = PERSONA_STYLES.get(persona_name)
    if entry:
        return entry["style"]
    return f"interviewer named {persona_name}"


def persona_voice_id(persona_name: str) -> str:
    """Return the ElevenLabs voice_id for a persona, falling back to the default voice."""
    entry = PERSONA_STYLES.get(persona_name)
    if entry and entry.get("voice_id"):
        return entry["voice_id"]
    return DEFAULT_INTERVIEWER_VOICE_ID


def elevenlabs_tts(text: str, voice_id: str | None = None) -> bytes:
    """
    Synthesize `text` to speech via the ElevenLabs API and return raw MP3 bytes.

    Raises RuntimeError with a human-readable message on missing key or API error.
    """
    import httpx

    api_key = load_env_key("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY not set — add it to .env in the project root")

    vid = voice_id or DEFAULT_INTERVIEWER_VOICE_ID
    resp = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{vid}",
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        },
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"ElevenLabs API {resp.status_code}: {resp.text[:200]}")
    return resp.content


def generate_persona_questions(episode_id: int, persona_name: str) -> dict:
    """
    Use Claude to rewrite the default questions for an episode in a specific interviewer style.
    Saves results as a new persona. Returns {persona, questions_count, persona_style}.
    """
    init_db()
    with _conn() as conn:
        row = conn.execute(
            """SELECT e.id, r.repo, r.org, r.description, r.total_commits,
                      r.first_commit_date, r.first_commit_msg, r.language
               FROM journey_episodes e
               JOIN journey_repos r ON r.id = e.repo_id
               WHERE e.id=?""",
            (episode_id,),
        ).fetchone()

    if not row:
        return {"error": "episode not found"}

    default_qs = get_episode_questions(episode_id, persona="default")
    if not default_qs:
        return {"error": "no default questions to restyle"}

    style = persona_style(persona_name)

    questions_block = "\n".join(
        f"{i+1}. [{q['question_type']}] {q['question_text']}"
        for i, q in enumerate(default_qs)
    )

    prompt = (
        f"You are a writing assistant rewriting interview questions in a specific style.\n\n"
        f"REPO CONTEXT:\n"
        f"- Repo: {row['org']}/{row['repo']}\n"
        f"- Description: {row['description'] or 'no description'}\n"
        f"- Commits: {row['total_commits']}\n"
        f"- First commit: {(row['first_commit_date'] or '')[:10]} — \"{row['first_commit_msg'] or ''}\"\n"
        f"- Language: {row['language'] or 'unknown'}\n\n"
        f"INTERVIEWER STYLE:\n{style}\n\n"
        f"ORIGINAL QUESTIONS (keep the same quantity and same question_type tags):\n{questions_block}\n\n"
        f"Rewrite each question in the interviewer's voice. "
        f"Keep the same information intent but transform the phrasing completely. "
        f"Return ONLY a JSON array of objects: "
        f'[{{"seq":1,"question_type":"origin","question_text":"..."}},...]\n'
        f"No extra text, no markdown fences."
    )

    import urllib.request as _req

    api_key = load_env_key("OPENROUTER_API_KEY")
    if not api_key:
        return {"error": "OPENROUTER_API_KEY not set — add it to .env in the project root"}

    payload = json.dumps({
        "model": "anthropic/claude-haiku-4-5",
        "max_tokens": 2048,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    request = _req.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://homelab-status.local",
        },
    )
    with _req.urlopen(request, timeout=60) as resp:
        result = json.loads(resp.read())
    raw = result["choices"][0]["message"]["content"].strip()
    # Strip markdown code fences if model wrapped the JSON
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    import json as _json
    try:
        rewritten = _json.loads(raw)
    except Exception:
        return {"error": f"Failed to parse Claude response: {raw[:200]}"}

    with _conn() as conn:
        existing = conn.execute(
            "SELECT COUNT(*) FROM journey_questions WHERE episode_id=? AND persona=?",
            (episode_id, persona_name),
        ).fetchone()[0]
        if existing:
            conn.execute(
                "DELETE FROM journey_questions WHERE episode_id=? AND persona=? AND is_edited=0",
                (episode_id, persona_name),
            )

        conn.executemany(
            """INSERT INTO journey_questions
               (episode_id, seq, question_text, question_type, data_source, data_ref, persona, is_edited)
               VALUES (?,?,?,?,?,?,?,0)""",
            [
                (episode_id, q.get("seq", i+1), q["question_text"], q.get("question_type", "general"),
                 "ai_persona", persona_name, persona_name)
                for i, q in enumerate(rewritten)
            ],
        )

    return {"persona": persona_name, "questions_count": len(rewritten), "style": style[:80]}


def get_episode_script(episode_id: int, persona: str = "default") -> dict:
    """
    Return a formatted Q+A script for an episode — all questions + answers in dialogue format.
    Omits unanswered questions.
    """
    init_db()
    with _conn() as conn:
        ep = conn.execute(
            "SELECT e.title, r.repo FROM journey_episodes e JOIN journey_repos r ON r.id=e.repo_id WHERE e.id=?",
            (episode_id,),
        ).fetchone()

    if not ep:
        return {"error": "episode not found"}

    qs = get_episode_questions(episode_id, persona=persona)
    lines = []
    for q in qs:
        lines.append({
            "speaker": "interviewer",
            "text": q["question_text"],
            "type": q.get("question_type", "general"),
        })
        if q.get("answer_text"):
            lines.append({
                "speaker": "mark",
                "text": q["answer_text"],
            })

    return {
        "episode_id": episode_id,
        "title": ep["repo"] if ep else "",
        "persona": persona,
        "lines": lines,
        "answered_count": sum(1 for q in qs if q.get("answer_text")),
        "total_questions": len(qs),
    }


def get_episode_deps(episode_id: int) -> dict:
    """Return {repo, deps} for the repo attached to an episode. Falls back to live scan."""
    import json as _json
    init_db()
    with _conn() as conn:
        row = conn.execute(
            """SELECT r.repo, r.deps_snapshot FROM journey_episodes e
               JOIN journey_repos r ON r.id = e.repo_id WHERE e.id=?""",
            (episode_id,),
        ).fetchone()
    if not row:
        return {"repo": None, "deps": {}}
    deps = _json.loads(row["deps_snapshot"]) if row["deps_snapshot"] else {}
    if not deps:
        deps = scan_repo_deps(row["repo"])
    return {"repo": row["repo"], "deps": deps}
