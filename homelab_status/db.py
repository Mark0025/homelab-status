"""SQLite persistence — check runs, API routes, business explanations, network topology, journey story layer."""

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(os.environ.get("STATUS_DB_PATH", str(Path.home() / ".local" / "share" / "homelab-status" / "status.db")))


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS check_runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            checked_at  TEXT NOT NULL,
            total       INTEGER,
            up          INTEGER,
            down        INTEGER
        );

        CREATE TABLE IF NOT EXISTS service_checks (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id           INTEGER REFERENCES check_runs(id),
            checked_at       TEXT NOT NULL,
            name             TEXT NOT NULL,
            url              TEXT NOT NULL,
            category         TEXT,
            status_code      INTEGER,
            reachable        INTEGER,
            redirect_is_auth INTEGER,
            redirected_to    TEXT,
            has_docs         INTEGER,
            docs_url         TEXT,
            has_health       INTEGER,
            health_status    TEXT,
            response_time_ms INTEGER,
            server_header    TEXT,
            page_title       TEXT,
            error            TEXT
        );

        CREATE TABLE IF NOT EXISTS api_routes (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            service_name     TEXT NOT NULL,
            service_url      TEXT NOT NULL,
            container_name   TEXT NOT NULL DEFAULT '',
            method           TEXT NOT NULL,
            path             TEXT NOT NULL,
            summary          TEXT,
            description      TEXT,
            business_summary TEXT,   -- plain-English explanation
            tags             TEXT,   -- JSON array
            parameters       TEXT,   -- JSON array
            request_body     TEXT,   -- JSON object
            responses        TEXT,   -- JSON object
            deprecated       INTEGER DEFAULT 0,
            discovered_at    TEXT NOT NULL,
            UNIQUE(service_name, method, path)
        );

        CREATE TABLE IF NOT EXISTS network_topology (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            container_name TEXT NOT NULL,
            network_name   TEXT NOT NULL,
            service_name   TEXT,
            connects_to    TEXT,  -- JSON array of container names
            updated_at     TEXT NOT NULL,
            UNIQUE(container_name, network_name)
        );

        CREATE INDEX IF NOT EXISTS idx_service_checks_name ON service_checks(name);
        CREATE INDEX IF NOT EXISTS idx_service_checks_run  ON service_checks(run_id);
        CREATE INDEX IF NOT EXISTS idx_api_routes_service  ON api_routes(service_name);
        CREATE INDEX IF NOT EXISTS idx_api_routes_container ON api_routes(container_name);
        CREATE INDEX IF NOT EXISTS idx_topology_container  ON network_topology(container_name);
        CREATE INDEX IF NOT EXISTS idx_topology_network    ON network_topology(network_name);

        -- ── JOURNEY STORY LAYER ────────────────────────────────────────────
        -- sources: the raw GitHub snapshot (immutable, timestamped — never delete rows)
        CREATE TABLE IF NOT EXISTS journey_repos (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            org           TEXT NOT NULL,
            repo          TEXT NOT NULL,
            created_at    TEXT,
            description   TEXT,
            is_fork       INTEGER DEFAULT 0,
            language      TEXT,
            topics        TEXT,   -- JSON array
            total_commits INTEGER DEFAULT 0,
            first_commit_date TEXT,
            first_commit_msg  TEXT,
            first_commit_sha  TEXT,
            last_commit_date  TEXT,
            last_commit_msg   TEXT,
            readme_preview    TEXT,
            has_docker    INTEGER DEFAULT 0,
            has_tests     INTEGER DEFAULT 0,
            has_ci        INTEGER DEFAULT 0,
            has_claude_md INTEGER DEFAULT 0,
            chapter       TEXT,   -- collecting_era | learning_era | building_era | going_all_in | infrastructure_era
            notes         TEXT,
            imported_at   TEXT NOT NULL,
            UNIQUE(org, repo)
        );

        -- facts: the 5 eras of Mark's journey
        CREATE TABLE IF NOT EXISTS journey_chapters (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,  -- e.g. 'collecting_era'
            title       TEXT NOT NULL,         -- e.g. 'The Collecting Era'
            start_date  TEXT NOT NULL,
            end_date    TEXT NOT NULL,
            narrative   TEXT,                  -- journalist's summary of this era
            created_at  TEXT NOT NULL
        );

        -- stories: one interview episode per repo/moment — filled in as interviews happen
        CREATE TABLE IF NOT EXISTS journey_episodes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            chapter_id   INTEGER REFERENCES journey_chapters(id),
            repo_id      INTEGER REFERENCES journey_repos(id),
            episode_num  INTEGER,
            title        TEXT,
            hook         TEXT,   -- the opening question / grabber line
            status       TEXT NOT NULL DEFAULT 'draft',  -- draft | scheduled | recorded | published
            recorded_at  TEXT,
            published_at TEXT,
            audio_url    TEXT,
            transcript   TEXT,
            created_at   TEXT NOT NULL
        );

        -- interview questions: the actual Q&A scaffold per episode
        CREATE TABLE IF NOT EXISTS journey_questions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            episode_id    INTEGER REFERENCES journey_episodes(id),
            seq           INTEGER NOT NULL,    -- question order within episode
            question_text TEXT NOT NULL,
            question_type TEXT,  -- origin | pivot | failure | vision | technical | personal
            data_source   TEXT,  -- gh_commit | gh_repo | pai_learning | yt_transcript | manual
            data_ref      TEXT,  -- sha, doc_id, url — the evidence this question is built on
            answer_text   TEXT,  -- filled in after interview
            recorded_at   TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_journey_repos_chapter ON journey_repos(chapter);
        CREATE INDEX IF NOT EXISTS idx_journey_repos_org     ON journey_repos(org, repo);
        CREATE INDEX IF NOT EXISTS idx_journey_episodes_status ON journey_episodes(status);
        CREATE INDEX IF NOT EXISTS idx_journey_questions_ep  ON journey_questions(episode_id);

        -- Add columns if upgrading from older schema
        """)
        # Idempotent column additions for journey tables
        for col, defn in [
            ("persona",     "TEXT NOT NULL DEFAULT 'default'"),   # interviewer persona
            ("is_edited",   "INTEGER NOT NULL DEFAULT 0"),        # 1 = human-edited, survives re-enrichment
            ("edited_at",   "TEXT"),
        ]:
            try:
                conn.execute(f"ALTER TABLE journey_questions ADD COLUMN {col} {defn}")
            except sqlite3.OperationalError:
                pass
        for col, defn in [
            ("deps_snapshot", "TEXT"),  # JSON: {npm:[...], pyproject:[...], requirements:[...]}
        ]:
            try:
                conn.execute(f"ALTER TABLE journey_repos ADD COLUMN {col} {defn}")
            except sqlite3.OperationalError:
                pass
        # Idempotent column additions for upgrades
        for col, defn in [
            ("container_name", "TEXT NOT NULL DEFAULT ''"),
            ("business_summary", "TEXT"),
        ]:
            try:
                conn.execute(f"ALTER TABLE api_routes ADD COLUMN {col} {defn}")
            except sqlite3.OperationalError:
                pass  # already exists


def _business_summary(method: str, path: str, summary: str, description: str, tags: list[str]) -> str:
    """Generate plain-English business explanation from OpenAPI metadata."""
    # Combine all available text
    raw = f"{summary} {description}".strip()
    m = method.upper()
    p = path.lower()

    # Build context clues
    is_read = m == "GET"
    is_create = m == "POST"
    is_update = m in ("PUT", "PATCH")
    is_delete = m == "DELETE"

    # Action word based on HTTP method
    if is_read:
        action = "Retrieves" if not p.endswith("s") or "/current" in p or "/status" in p or "/health" in p else "Lists"
    elif is_create:
        action = "Creates"
    elif is_update:
        action = "Updates"
    elif is_delete:
        action = "Deletes"
    else:
        action = "Handles"

    # If summary is already plain English and short, use it
    if summary and len(summary) > 10 and not summary.startswith("{") and "/" not in summary[:15]:
        base = summary.strip().rstrip(".")
        if not base[0].isupper():
            base = base[0].upper() + base[1:]
        return f"{base}. {description.strip()[:200]}" if description and description != summary else base

    # Fall back to path-based explanation
    parts = [p for p in path.strip("/").split("/") if p and not p.startswith("{")]
    readable = " → ".join(parts).replace("-", " ").replace("_", " ")
    return f"{action} {readable}."


def save_run(results: list, checked_at: datetime) -> int:
    init_db()
    ts = checked_at.isoformat()
    up = sum(1 for r in results if r.reachable and not r.error)

    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO check_runs (checked_at, total, up, down) VALUES (?,?,?,?)",
            (ts, len(results), up, len(results) - up),
        )
        run_id = cur.lastrowid
        conn.executemany(
            """INSERT INTO service_checks
               (run_id, checked_at, name, url, category, status_code, reachable,
                redirect_is_auth, redirected_to, has_docs, docs_url, has_health,
                health_status, response_time_ms, server_header, page_title, error)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [(
                run_id, ts,
                r.service.name, r.service.url, r.service.category,
                r.status_code, int(r.reachable), int(r.redirect_is_auth),
                r.redirected_to, int(r.has_docs), r.docs_url,
                int(r.has_health), r.health_status,
                int(r.response_time_ms), r.server_header, r.title, r.error,
            ) for r in results],
        )
    return run_id


def save_routes(service_name: str, service_url: str, routes: list, container_name: str = "") -> int:
    """Upsert discovered OpenAPI routes with business summaries. Returns count saved."""
    init_db()
    ts = datetime.now().isoformat()
    saved = 0
    with _conn() as conn:
        for route in routes:
            r = route.model_dump() if hasattr(route, "model_dump") else route
            tags = r.get("tags", [])
            biz = _business_summary(
                r["method"], r["path"],
                r.get("summary", ""), r.get("description", ""), tags
            )
            conn.execute(
                """INSERT INTO api_routes
                   (service_name, service_url, container_name, method, path,
                    summary, description, business_summary,
                    tags, parameters, request_body, responses, deprecated, discovered_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(service_name, method, path) DO UPDATE SET
                     summary=excluded.summary,
                     description=excluded.description,
                     business_summary=excluded.business_summary,
                     container_name=excluded.container_name,
                     tags=excluded.tags,
                     parameters=excluded.parameters,
                     request_body=excluded.request_body,
                     responses=excluded.responses,
                     deprecated=excluded.deprecated,
                     discovered_at=excluded.discovered_at""",
                (
                    service_name, service_url, container_name,
                    r["method"], r["path"],
                    r.get("summary", ""), r.get("description", ""), biz,
                    json.dumps(tags),
                    json.dumps(r.get("parameters", [])),
                    json.dumps(r.get("request_body")),
                    json.dumps(r.get("responses", {})),
                    int(r.get("deprecated", False)),
                    ts,
                ),
            )
            saved += 1
    return saved


def save_network_topology(services: list) -> None:
    """Upsert network topology from Service model data."""
    init_db()
    ts = datetime.now().isoformat()
    with _conn() as conn:
        for svc in services:
            for network in svc.docker_networks:
                conn.execute(
                    """INSERT INTO network_topology
                       (container_name, network_name, service_name, connects_to, updated_at)
                       VALUES (?,?,?,?,?)
                       ON CONFLICT(container_name, network_name) DO UPDATE SET
                         service_name=excluded.service_name,
                         connects_to=excluded.connects_to,
                         updated_at=excluded.updated_at""",
                    (
                        svc.container_name, network,
                        svc.name, json.dumps(svc.connects_to), ts,
                    ),
                )


def get_routes(service_name: str | None = None) -> list[dict]:
    init_db()
    with _conn() as conn:
        if service_name:
            rows = conn.execute(
                "SELECT * FROM api_routes WHERE service_name LIKE ? ORDER BY path, method",
                (f"%{service_name}%",),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM api_routes ORDER BY service_name, path, method"
            ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        for field in ("tags", "parameters", "request_body", "responses"):
            try:
                d[field] = json.loads(d[field]) if d[field] else None
            except Exception:
                pass
        result.append(d)
    return result


def get_topology() -> list[dict]:
    init_db()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM network_topology ORDER BY network_name, container_name"
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["connects_to"] = json.loads(d["connects_to"]) if d["connects_to"] else []
        except Exception:
            d["connects_to"] = []
        result.append(d)
    return result


def get_history(limit: int = 10) -> list[dict]:
    init_db()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM check_runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_latest_checks() -> list[dict]:
    init_db()
    with _conn() as conn:
        rows = conn.execute("""
            SELECT sc.* FROM service_checks sc
            INNER JOIN (
                SELECT name, MAX(id) AS max_id FROM service_checks GROUP BY name
            ) latest ON sc.id = latest.max_id
            ORDER BY sc.name
        """).fetchall()
    return [dict(r) for r in rows]
