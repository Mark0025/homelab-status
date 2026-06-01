"""FastAPI web server — live dashboard of homelab endpoint status."""

import asyncio
from datetime import datetime

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from loguru import logger

from .checker import CheckResult, check_all
from .db import get_history, get_routes, get_topology, save_network_topology, save_routes, save_run
from .git_history import (
    get_commit_stats, get_recent_commits, get_repo_summaries,
    refresh_all, _refresh_running, SKIP_REPOS,
)
from .timeline import (
    build_commit_timeline, build_pr_timeline,
    enrich_all_commits, get_commit_type_stats, get_pr_list, refresh_prs,
)
from .project_intel import (
    enrich_commits_with_agents, get_agent_stats, get_all_profiles,
    get_project_profile, extract_fix_patterns, search_profiles,
    refresh_all_profiles, _profile_running as _intel_running,
)
from .services import CATEGORY_LABELS, SERVICES
from .mdops import doc_stats, docs_for_repo, get_doc, grade_doc, list_projects, search_docs

api = FastAPI(title="Homelab Status", docs_url=None, redoc_url=None)

_cache: dict = {"results": [], "checked_at": None, "running": False}
_CACHE_TTL = 60  # seconds


async def _run_checks() -> None:
    if _cache["running"]:
        return
    _cache["running"] = True
    logger.info("Running endpoint checks...")
    try:
        results = await check_all(SERVICES, concurrency=20)
        _cache["results"] = results
        _cache["checked_at"] = datetime.now()

        # Persist to SQLite
        run_id = save_run(results, _cache["checked_at"])
        logger.info(f"Saved run #{run_id} to SQLite")

        # Persist discovered OpenAPI routes with container_name + business summaries
        for r in results:
            if r.api_routes:
                n = save_routes(
                    r.service.name, r.service.url, r.api_routes,
                    container_name=r.service.container_name,
                )
                logger.debug(f"Saved {n} routes for {r.service.name}")

        # Persist network topology
        save_network_topology(SERVICES)

        total_routes = sum(len(r.api_routes) for r in results)
        logger.info(f"Done — {len(results)} endpoints, {total_routes} API routes discovered")
    finally:
        _cache["running"] = False


def _result_to_dict(r: CheckResult) -> dict:
    return {
        "name": r.service.name,
        "url": r.service.url,
        "category": r.service.category,
        "category_label": CATEGORY_LABELS.get(r.service.category, r.service.category),
        "description": r.service.description,
        "what_it_does": r.service.what_it_does,
        "repo": r.service.repo,
        "container_name": r.service.container_name,
        "docker_networks": r.service.docker_networks,
        "connects_to": r.service.connects_to,
        "status_code": r.status_code,
        "reachable": r.reachable,
        "redirect_is_auth": r.redirect_is_auth,
        "redirected_to": r.redirected_to,
        "has_docs": r.has_docs,
        "docs_url": r.docs_url,
        "has_health": r.has_health,
        "health_status": r.health_status,
        "response_time_ms": round(r.response_time_ms),
        "server_header": r.server_header,
        "title": r.title,
        "error": r.error,
        "route_count": len(r.api_routes),
    }


@api.get("/api/status")
async def api_status(force: bool = Query(False)):
    if force or not _cache["results"]:
        await _run_checks()
    elif _cache["checked_at"]:
        age = (datetime.now() - _cache["checked_at"]).total_seconds()
        if age > _CACHE_TTL:
            asyncio.create_task(_run_checks())

    results = _cache["results"]
    total_routes = sum(len(r.api_routes) for r in results)
    return JSONResponse({
        "checked_at": _cache["checked_at"].isoformat() if _cache["checked_at"] else None,
        "running": _cache["running"],
        "total": len(results),
        "up": sum(1 for r in results if r.reachable and not r.error),
        "down": sum(1 for r in results if not r.reachable or r.error),
        "auth_wall": sum(1 for r in results if r.redirect_is_auth),
        "with_docs": sum(1 for r in results if r.has_docs),
        "total_api_routes": total_routes,
        "services": [_result_to_dict(r) for r in results],
    })


@api.get("/api/routes")
async def api_routes(service: str | None = Query(None)):
    """Return all discovered API routes from SQLite."""
    rows = get_routes(service)
    import json
    for r in rows:
        for field in ("tags", "parameters", "request_body", "responses"):
            try:
                r[field] = json.loads(r[field]) if r[field] else None
            except Exception:
                pass
    return JSONResponse({"total": len(rows), "routes": rows})


@api.get("/api/topology")
async def api_topology():
    """Return network topology — which containers are on which networks and what they connect to."""
    rows = get_topology()
    # Group by network
    by_network: dict[str, list] = {}
    for r in rows:
        by_network.setdefault(r["network_name"], []).append(r)
    return JSONResponse({"networks": by_network, "total_containers": len(rows)})


@api.get("/api/history")
async def api_history():
    return JSONResponse({"runs": get_history(20)})


# ── Git history endpoints ─────────────────────────────────────────────────────

@api.get("/api/git/stats")
async def git_stats():
    """Aggregate commit stats — fast, reads from cache."""
    stats = get_commit_stats()
    if not stats["total_commits"] and not _refresh_running:
        # First time: kick off background refresh, return empty
        asyncio.create_task(refresh_all())
    return JSONResponse(stats)


@api.get("/api/git/commits")
async def git_commits(
    limit: int = Query(10000, ge=1, le=100000),
    repo: str | None = Query(None),
    owner: str | None = Query(None),
):
    """Recent commits across all repos — always from SQLite cache."""
    rows = get_recent_commits(limit=limit, repo=repo, owner=owner)
    return JSONResponse({"total": len(rows), "commits": rows})


@api.get("/api/git/repos")
async def git_repos():
    """All repos with commit counts and last activity — from cache."""
    rows = get_repo_summaries()
    return JSONResponse({"total": len(rows), "repos": rows})


@api.post("/api/git/refresh")
async def git_refresh(force: bool = Query(True)):
    """Trigger a background refresh from GitHub API. Returns immediately."""
    if _refresh_running:
        return JSONResponse({"status": "already_running"})
    asyncio.create_task(refresh_all(force=force))
    return JSONResponse({"status": "refresh_started"})


# ── Timeline endpoints ────────────────────────────────────────────────────────

@api.get("/api/timeline/commits", response_class=HTMLResponse)
async def timeline_commits(
    repo: str | None = Query(None),
    owner: str | None = Query(None),
    since: str | None = Query(None),
    group_by: str = Query("type"),
    include_bots: bool = Query(False),
):
    """Return Plotly commit timeline as HTML fragment (no full page wrapper)."""
    html = build_commit_timeline(
        repo=repo, owner=owner, since=since,
        group_by=group_by, include_bots=include_bots,
    )
    return HTMLResponse(html)


@api.get("/api/timeline/prs", response_class=HTMLResponse)
async def timeline_prs(
    repo: str | None = Query(None),
    owner: str | None = Query(None),
):
    html = build_pr_timeline(repo=repo, owner=owner)
    return HTMLResponse(html)


@api.get("/api/timeline/stats")
async def timeline_stats(repo: str | None = Query(None)):
    return JSONResponse(get_commit_type_stats(repo=repo))


@api.get("/api/timeline/prs/list")
async def timeline_pr_list(repo: str | None = Query(None), limit: int = Query(200)):
    return JSONResponse({"prs": get_pr_list(repo=repo, limit=limit)})


@api.post("/api/timeline/refresh-prs")
async def timeline_refresh_prs():
    """Fetch PRs from GitHub for all repos in background."""
    asyncio.create_task(refresh_prs())
    return JSONResponse({"status": "pr_refresh_started"})


# ── Project Intelligence endpoints ───────────────────────────────────────────

@api.get("/api/intel/agent-stats")
async def intel_agent_stats():
    enrich_commits_with_agents()
    return JSONResponse(get_agent_stats())


@api.get("/api/intel/profiles")
async def intel_profiles(active_only: bool = Query(True), q: str | None = Query(None)):
    if q:
        return JSONResponse({"profiles": search_profiles(q)})
    return JSONResponse({"profiles": get_all_profiles(active_only=active_only)})


@api.get("/api/intel/profile/{owner}/{repo}")
async def intel_profile(owner: str, repo: str):
    profile = get_project_profile(repo, owner)
    if not profile:
        return JSONResponse({"error": "not profiled yet"}, status_code=404)
    return JSONResponse(profile)


@api.get("/api/intel/fixes")
async def intel_fixes(repo: str | None = Query(None), limit: int = Query(100)):
    fixes = extract_fix_patterns(repo=repo)
    return JSONResponse({"total": len(fixes), "fixes": fixes[:limit]})


@api.post("/api/intel/refresh")
async def intel_refresh():
    if _intel_running:
        return JSONResponse({"status": "already_running"})
    asyncio.create_task(refresh_all_profiles())
    return JSONResponse({"status": "profile_refresh_started"})


@api.get("/api/mdops/stats")
async def mdops_stats():
    return JSONResponse(doc_stats())


@api.get("/api/mdops/projects")
async def mdops_projects(limit: int = Query(100)):
    return JSONResponse(list_projects(limit=limit))


@api.get("/api/mdops/search")
async def mdops_search(q: str = Query(""), limit: int = Query(50), git_only: bool = Query(False)):
    if not q.strip():
        return JSONResponse([])
    return JSONResponse(search_docs(q.strip(), limit=limit, git_only=git_only))


@api.get("/api/mdops/doc/{doc_id}")
async def mdops_doc(doc_id: int):
    doc = get_doc(doc_id)
    if not doc:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(doc)


@api.get("/api/mdops/grade/{doc_id}")
async def mdops_grade(doc_id: int):
    return JSONResponse(grade_doc(doc_id))


@api.get("/api/mdops/repo/{repo_name}")
async def mdops_repo_docs(repo_name: str):
    return JSONResponse(docs_for_repo(repo_name))


@api.get("/", response_class=HTMLResponse)
async def dashboard():
    if not _cache["results"]:
        asyncio.create_task(_run_checks())
    return HTMLResponse(_HTML)


_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Homelab Status</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js" charset="utf-8"></script>
<style>
  :root {
    --bg: #0f1117; --surface: #1a1d27; --surface2: #252836;
    --border: #2e3148; --text: #e2e8f0; --muted: #64748b;
    --green: #22c55e; --red: #ef4444; --yellow: #f59e0b;
    --cyan: #06b6d4; --blue: #3b82f6; --purple: #a855f7;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: system-ui, sans-serif; font-size: 14px; }

  header {
    background: var(--surface); border-bottom: 1px solid var(--border);
    padding: 14px 24px; display: flex; align-items: center;
    justify-content: space-between; position: sticky; top: 0; z-index: 10;
  }
  header h1 { font-size: 18px; font-weight: 700; }
  header h1 span { color: var(--blue); }
  .header-right { display: flex; align-items: center; gap: 12px; }
  #checked-at { color: var(--muted); font-size: 12px; }
  #refresh-btn {
    background: var(--blue); color: #fff; border: none; border-radius: 6px;
    padding: 6px 14px; cursor: pointer; font-size: 13px; font-weight: 600;
  }
  #refresh-btn:disabled { opacity: 0.5; cursor: default; }

  .tabs {
    display: flex; gap: 0; border-bottom: 1px solid var(--border);
    padding: 0 24px; background: var(--surface);
  }
  .tab {
    padding: 10px 18px; cursor: pointer; border-bottom: 2px solid transparent;
    font-size: 13px; font-weight: 500; color: var(--muted); transition: all 0.15s;
  }
  .tab:hover { color: var(--text); }
  .tab.active { color: var(--blue); border-bottom-color: var(--blue); }

  .summary {
    display: flex; gap: 12px; flex-wrap: wrap; padding: 16px 24px;
  }
  .stat {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 12px 20px; min-width: 110px;
  }
  .stat .num { font-size: 26px; font-weight: 800; line-height: 1; }
  .stat .lbl { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); margin-top: 4px; }

  .controls {
    padding: 0 24px 12px;
    display: flex; gap: 8px; flex-wrap: wrap; align-items: center;
  }
  .filter-btn {
    background: var(--surface2); border: 1px solid var(--border);
    color: var(--muted); border-radius: 20px; padding: 4px 14px;
    cursor: pointer; font-size: 12px; transition: all 0.15s;
  }
  .filter-btn:hover { color: var(--text); border-color: var(--blue); }
  .filter-btn.active { background: var(--blue); color: #fff; border-color: var(--blue); }
  .search-wrap { margin-left: auto; }
  #search {
    background: var(--surface2); border: 1px solid var(--border);
    color: var(--text); border-radius: 6px; padding: 5px 12px;
    font-size: 13px; outline: none; width: 220px;
  }
  #search:focus { border-color: var(--blue); }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 12px; padding: 0 24px 24px;
  }
  .card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 14px 16px;
    display: flex; flex-direction: column; gap: 8px;
    transition: border-color 0.15s;
  }
  .card:hover { border-color: #4e5580; }
  .card.up    { border-left: 3px solid var(--green); }
  .card.down  { border-left: 3px solid var(--red); }
  .card.auth  { border-left: 3px solid var(--cyan); }
  .card.timeout { border-left: 3px solid var(--yellow); }

  .card-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
  .card-name { font-weight: 700; font-size: 14px; }
  .card-cat  { font-size: 11px; color: var(--muted); margin-top: 1px; }
  .badge { border-radius: 5px; padding: 2px 8px; font-size: 11px; font-weight: 700; white-space: nowrap; }
  .badge.up      { background: rgba(34,197,94,0.15); color: var(--green); }
  .badge.down    { background: rgba(239,68,68,0.15); color: var(--red); }
  .badge.auth    { background: rgba(6,182,212,0.15); color: var(--cyan); }
  .badge.timeout { background: rgba(245,158,11,0.15); color: var(--yellow); }
  .card-desc   { color: var(--muted); font-size: 12px; line-height: 1.5; }
  .card-detail { font-size: 12px; color: #94a3b8; line-height: 1.5; }
  .card-meta   { display: flex; flex-wrap: wrap; gap: 6px; }
  .pill {
    font-size: 11px; border-radius: 4px; padding: 1px 7px;
    background: var(--surface2); border: 1px solid var(--border); color: var(--muted);
  }
  .pill a { color: inherit; text-decoration: none; }
  .pill a:hover { color: var(--blue); }
  .pill.docs   { background: rgba(59,130,246,0.1); color: var(--blue); border-color: rgba(59,130,246,0.3); }
  .pill.health { background: rgba(34,197,94,0.1); color: var(--green); border-color: rgba(34,197,94,0.3); }
  .pill.repo   { background: rgba(168,85,247,0.1); color: var(--purple); border-color: rgba(168,85,247,0.3); }
  .pill.routes { background: rgba(245,158,11,0.1); color: var(--yellow); border-color: rgba(245,158,11,0.3); cursor: pointer; }
  .pill.fast   { color: var(--green); }
  .pill.slow   { color: var(--yellow); }
  .pill.very-slow { color: var(--red); }
  .card-url  { font-size: 11px; color: var(--muted); }
  .card-url a { color: inherit; text-decoration: none; }
  .card-url a:hover { color: var(--blue); }
  .card-error { font-size: 11px; color: #f87171; background: rgba(239,68,68,0.08); border-radius: 4px; padding: 4px 8px; }

  /* Routes tab */
  #routes-view { padding: 16px 24px; }
  .route-table { width: 100%; border-collapse: collapse; font-size: 12px; }
  .route-table th {
    text-align: left; padding: 8px 12px;
    background: var(--surface); border-bottom: 1px solid var(--border);
    color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em;
    position: sticky; top: 50px;
  }
  .route-table td { padding: 7px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }
  .route-table tr:hover td { background: var(--surface2); }
  .method { font-weight: 700; font-size: 11px; border-radius: 3px; padding: 1px 6px; }
  .method.GET    { background: rgba(34,197,94,0.15); color: var(--green); }
  .method.POST   { background: rgba(59,130,246,0.15); color: var(--blue); }
  .method.PUT    { background: rgba(245,158,11,0.15); color: var(--yellow); }
  .method.PATCH  { background: rgba(168,85,247,0.15); color: var(--purple); }
  .method.DELETE { background: rgba(239,68,68,0.15); color: var(--red); }
  .route-path { font-family: monospace; color: #94a3b8; }
  .route-summary { color: var(--text); }
  .route-svc { font-size: 11px; color: var(--muted); }
  .route-tags { display: flex; gap: 4px; flex-wrap: wrap; }
  .tag-chip { font-size: 10px; border-radius: 3px; padding: 1px 5px; background: var(--surface2); color: var(--muted); }
  #route-search-wrap { padding: 12px 24px 8px; }
  #route-search {
    background: var(--surface2); border: 1px solid var(--border);
    color: var(--text); border-radius: 6px; padding: 5px 12px;
    font-size: 13px; outline: none; width: 380px;
  }
  #route-search:focus { border-color: var(--blue); }

  .loading { text-align: center; padding: 80px 24px; color: var(--muted); }
  .spinner {
    display: inline-block; width: 32px; height: 32px;
    border: 3px solid var(--border); border-top-color: var(--blue);
    border-radius: 50%; animation: spin 0.8s linear infinite; margin-bottom: 12px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .section-header {
    grid-column: 1/-1; display: flex; align-items: center; gap: 10px;
    padding: 6px 0 2px; border-bottom: 1px solid var(--border); margin-bottom: 4px;
  }
  .section-header h2 { font-size: 13px; font-weight: 700; }
  .section-header .count { font-size: 12px; color: var(--muted); }
  #no-results { grid-column: 1/-1; text-align: center; color: var(--muted); padding: 40px; }
</style>
</head>
<body>

<header>
  <h1>🏠 <span>Homelab</span> Status</h1>
  <div class="header-right">
    <span id="checked-at">Loading...</span>
    <button id="refresh-btn" onclick="refresh()">Refresh</button>
  </div>
</header>

<div class="tabs">
  <div class="tab active" onclick="showTab('services', this)">Services</div>
  <div class="tab" onclick="showTab('routes', this)">API Routes <span id="route-count-badge" style="color:var(--yellow);font-size:11px"></span></div>
  <div class="tab" onclick="showTab('git', this)">Git History <span id="git-count-badge" style="color:var(--green);font-size:11px"></span></div>
  <div class="tab" onclick="showTab('timeline', this)">Timeline &amp; Analytics</div>
  <div class="tab" onclick="showTab('intel', this)">Dev Intelligence</div>
  <div class="tab" onclick="showTab('plans', this)">Plans &amp; Docs <span id="plans-count-badge" style="color:var(--muted);font-size:11px"></span></div>
</div>

<!-- SERVICES TAB -->
<div id="services-view">
  <div class="summary" id="summary"></div>
  <div class="controls">
    <button class="filter-btn active" data-cat="all" onclick="setFilter('all', this)">All</button>
    <button class="filter-btn" data-cat="terry" onclick="setFilter('terry', this)">Terry</button>
    <button class="filter-btn" data-cat="pete" onclick="setFilter('pete', this)">Pete</button>
    <button class="filter-btn" data-cat="ai" onclick="setFilter('ai', this)">AI/LLM</button>
    <button class="filter-btn" data-cat="monitoring" onclick="setFilter('monitoring', this)">Monitoring</button>
    <button class="filter-btn" data-cat="infrastructure" onclick="setFilter('infrastructure', this)">Infra</button>
    <button class="filter-btn" data-cat="voice" onclick="setFilter('voice', this)">Voice</button>
    <button class="filter-btn" data-cat="sites" onclick="setFilter('sites', this)">Sites</button>
    <button class="filter-btn" data-cat="tools" onclick="setFilter('tools', this)">Tools</button>
    <button class="filter-btn" data-cat="problems" onclick="setFilter('problems', this)" style="color:#ef4444;border-color:#ef4444">⚠ Problems</button>
    <div class="search-wrap">
      <input id="search" type="text" placeholder="Search services..." oninput="renderServices()">
    </div>
  </div>
  <div class="grid" id="grid">
    <div class="loading" style="grid-column:1/-1">
      <div class="spinner"></div><br>Checking all endpoints...
    </div>
  </div>
</div>

<!-- TIMELINE TAB -->
<div id="timeline-view" style="display:none;padding:16px 24px">
  <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:16px">
    <select id="tl-repo" onchange="loadTimeline()"
      style="background:var(--surface2);border:1px solid var(--border);color:var(--text);border-radius:6px;padding:5px 10px;font-size:12px">
      <option value="">All repos</option>
    </select>
    <select id="tl-group" onchange="loadTimeline()"
      style="background:var(--surface2);border:1px solid var(--border);color:var(--text);border-radius:6px;padding:5px 10px;font-size:12px">
      <option value="type">Group by: Commit Type</option>
      <option value="repo">Group by: Repo</option>
      <option value="author">Group by: Author</option>
      <option value="strategy">Group by: Merge Strategy</option>
      <option value="impact">Group by: Impact Size</option>
    </select>
    <select id="tl-since" onchange="loadTimeline()"
      style="background:var(--surface2);border:1px solid var(--border);color:var(--text);border-radius:6px;padding:5px 10px;font-size:12px">
      <option value="">All time</option>
      <option value="2026-01-01">2026</option>
      <option value="2025-01-01">2025+</option>
      <option value="2024-01-01">2024+</option>
      <option value="2023-01-01">2023+</option>
    </select>
    <label style="font-size:12px;color:var(--muted);display:flex;align-items:center;gap:4px">
      <input type="checkbox" id="tl-bots" onchange="loadTimeline()"> Include bots
    </label>
    <div style="border-left:1px solid var(--border);height:20px;margin:0 4px"></div>
    <button onclick="switchTimelineView('commits')" id="btn-commits"
      style="background:var(--blue);color:#fff;border:none;border-radius:6px;padding:5px 14px;cursor:pointer;font-size:12px">
      Commits
    </button>
    <button onclick="switchTimelineView('prs')" id="btn-prs"
      style="background:var(--surface2);border:1px solid var(--border);color:var(--muted);border-radius:6px;padding:5px 14px;cursor:pointer;font-size:12px">
      PR Lifecycle
    </button>
    <button onclick="triggerPRRefresh()"
      style="background:var(--surface2);border:1px solid var(--border);color:var(--muted);border-radius:6px;padding:5px 14px;cursor:pointer;font-size:12px">
      ↻ Fetch PRs
    </button>
    <span id="tl-status" style="font-size:11px;color:var(--muted)"></span>
  </div>
  <div id="plotly-container">
    <div class="loading"><div class="spinner"></div><br>Building timeline...</div>
  </div>
</div>

<!-- INTELLIGENCE TAB -->
<div id="intel-view" style="display:none;padding:16px 24px">

  <!-- Agent Attribution Stats strip -->
  <div id="intel-agent-strip" style="margin-bottom:20px"></div>

  <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:16px">
    <div style="display:flex;gap:6px">
      <button onclick="showIntelView('fixes')" id="btn-intel-fixes"
        style="background:var(--blue);color:#fff;border:none;border-radius:6px;padding:5px 14px;cursor:pointer;font-size:12px">
        Fix Patterns
      </button>
      <button onclick="showIntelView('repos')" id="btn-intel-repos"
        style="background:var(--surface2);border:1px solid var(--border);color:var(--muted);border-radius:6px;padding:5px 14px;cursor:pointer;font-size:12px">
        Repo Intelligence
      </button>
    </div>
    <input id="intel-search" type="text" placeholder="Search repos by purpose, what it does..."
      style="background:var(--surface2);border:1px solid var(--border);color:var(--text);border-radius:6px;padding:5px 12px;font-size:13px;outline:none;width:320px"
      oninput="searchIntel()">
    <button onclick="triggerIntelRefresh()"
      style="background:var(--surface2);border:1px solid var(--border);color:var(--muted);border-radius:6px;padding:5px 14px;cursor:pointer;font-size:12px;margin-left:auto">
      ↻ Profile Repos
    </button>
    <span id="intel-status" style="font-size:11px;color:var(--muted)"></span>
  </div>

  <div id="intel-content">
    <div class="loading"><div class="spinner"></div><br>Loading intelligence...</div>
  </div>
</div>

<!-- PLANS & DOCS TAB -->
<div id="plans-view" style="display:none;padding:16px 24px">

  <!-- Stats strip -->
  <div id="plans-stats-strip" style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px"></div>

  <!-- Controls -->
  <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:16px">
    <input id="plans-search" type="text" placeholder="Search .md plans, specs, designs..."
      style="background:var(--surface2);border:1px solid var(--border);color:var(--text);border-radius:6px;padding:6px 14px;font-size:13px;outline:none;width:360px"
      oninput="plansSearch()">
    <label style="font-size:12px;color:var(--muted);display:flex;align-items:center;gap:6px;cursor:pointer">
      <input type="checkbox" id="plans-git-only" onchange="plansSearch()" style="cursor:pointer">
      Git-tracked only
    </label>
    <button onclick="plansLoadProjects()"
      style="background:var(--surface2);border:1px solid var(--border);color:var(--muted);border-radius:6px;padding:5px 14px;cursor:pointer;font-size:12px;margin-left:auto">
      Browse Projects
    </button>
    <span id="plans-status" style="font-size:11px;color:var(--muted)"></span>
  </div>

  <!-- Results -->
  <div id="plans-content">
    <div style="color:var(--muted);font-size:13px;padding:20px 0">
      Search for a plan, spec, or design doc above — or click <strong>Browse Projects</strong> to see all indexed projects.
    </div>
  </div>

  <!-- Detail panel (slides in) -->
  <div id="plans-detail" style="display:none;position:fixed;top:0;right:0;width:680px;height:100vh;
    background:var(--surface);border-left:1px solid var(--border);overflow-y:auto;z-index:100;padding:24px">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <strong id="plans-detail-title" style="font-size:14px;color:var(--text)"></strong>
      <button onclick="closePlansDetail()"
        style="background:none;border:none;color:var(--muted);cursor:pointer;font-size:18px">✕</button>
    </div>
    <div id="plans-detail-body"></div>
  </div>
</div>

<!-- GIT TAB -->
<div id="git-view" style="display:none">
  <div style="padding:16px 24px 0">
    <div id="git-stats" style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px"></div>
    <div style="display:flex;gap:12px;align-items:center;margin-bottom:12px">
      <input id="git-search" type="text" placeholder="Search commits by message, repo, author..."
        style="background:var(--surface2);border:1px solid var(--border);color:var(--text);border-radius:6px;padding:5px 12px;font-size:13px;outline:none;width:380px"
        oninput="renderCommits()">
      <select id="git-repo-filter" onchange="loadCommits(this.value)"
        style="background:var(--surface2);border:1px solid var(--border);color:var(--text);border-radius:6px;padding:5px 10px;font-size:12px">
        <option value="">All repos</option>
      </select>
      <button onclick="triggerGitRefresh()"
        style="background:var(--surface2);border:1px solid var(--border);color:var(--muted);border-radius:6px;padding:5px 14px;cursor:pointer;font-size:12px">
        ↻ Refresh from GitHub
      </button>
      <span id="git-refresh-status" style="font-size:11px;color:var(--muted)"></span>
    </div>
    <div id="git-commits-container">
      <div class="loading"><div class="spinner"></div><br>Loading git history...</div>
    </div>
  </div>
</div>

<!-- ROUTES TAB -->
<div id="routes-view" style="display:none">
  <div id="route-search-wrap">
    <input id="route-search" type="text" placeholder="Search routes by path, method, service, summary..." oninput="renderRoutes()">
  </div>
  <div id="routes-container">
    <div class="loading"><div class="spinner"></div><br>Loading routes...</div>
  </div>
</div>

<script>
let allData = null;
let allRoutes = null;
let activeFilter = 'all';
let activeTab = 'services';

// ── Tab switching ─────────────────────────────────────────────────────────
function showTab(name, el) {
  activeTab = name;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('services-view').style.display = name === 'services' ? '' : 'none';
  document.getElementById('routes-view').style.display = name === 'routes' ? '' : 'none';
  document.getElementById('git-view').style.display = name === 'git' ? '' : 'none';
  document.getElementById('timeline-view').style.display = name === 'timeline' ? '' : 'none';
  document.getElementById('intel-view').style.display = name === 'intel' ? '' : 'none';
  document.getElementById('plans-view').style.display = name === 'plans' ? '' : 'none';
  if (name === 'routes' && !allRoutes) loadRoutes();
  if (name === 'git') loadGitHistory();
  if (name === 'timeline') initTimeline();
  if (name === 'intel') initIntel();
  if (name === 'plans') initPlans();
}

// ── Dev Intelligence tab ──────────────────────────────────────────────────
let intelView = 'fixes';
let intelAgentData = null;

const AGENT_COLORS = {
  'claude-code': '#a855f7', 'cursor': '#3b82f6', 'mixed': '#f59e0b',
  'human': '#22c55e', 'copilot': '#06b6d4', 'aider': '#ec4899', 'other': '#64748b',
};
const MODEL_ICONS = {
  'Claude Opus': '🟣', 'Claude Sonnet': '🔵', 'Claude Haiku': '🟢',
};

async function initIntel() {
  const [agentResp] = await Promise.all([fetch('/api/intel/agent-stats')]);
  intelAgentData = await agentResp.json();
  renderAgentStrip(intelAgentData);
  showIntelView('fixes');
}

function renderAgentStrip(d) {
  if (!d) return;
  const total = d.total_commits || 1;
  const byAgent = d.by_agent || {};
  const pills = Object.entries(byAgent)
    .sort((a,b) => b[1]-a[1])
    .map(([agent, cnt]) => {
      const pct = ((cnt/total)*100).toFixed(1);
      const col = AGENT_COLORS[agent] || '#64748b';
      return `<div class="stat" style="border-left:3px solid ${col};min-width:140px">
        <div style="font-size:20px;font-weight:800;color:${col}">${pct}%</div>
        <div style="font-size:11px;color:var(--muted)">${agent}</div>
        <div style="font-size:10px;color:#334155">${cnt.toLocaleString()} commits</div>
      </div>`;
    }).join('');

  const models = (d.by_model||[]).slice(0,4).map(m => {
    const icon = Object.entries(MODEL_ICONS).find(([k]) => (m.claude_model||'').includes(k));
    return `<span style="font-size:11px;color:#a855f7;background:rgba(168,85,247,0.1);padding:2px 8px;border-radius:4px;margin-right:4px">
      ${icon ? icon[1] : '🤖'} ${m.claude_model||'?'} (${m.cnt})
    </span>`;
  }).join('');

  document.getElementById('intel-agent-strip').innerHTML = `
    <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px">${pills}</div>
    <div style="font-size:12px;color:var(--muted);margin-bottom:4px">Claude models used:</div>
    <div>${models}</div>
  `;
}

function showIntelView(view) {
  intelView = view;
  ['fixes','repos'].forEach(v => {
    const btn = document.getElementById('btn-intel-' + v);
    if (btn) {
      btn.style.background = v === view ? 'var(--blue)' : 'var(--surface2)';
      btn.style.color = v === view ? '#fff' : 'var(--muted)';
      btn.style.border = v === view ? 'none' : '1px solid var(--border)';
    }
  });
  if (view === 'fixes') loadFixes();
  else if (view === 'repos') loadRepoProfiles();
}

async function loadFixes(repo) {
  const url = repo ? '/api/intel/fixes?repo=' + encodeURIComponent(repo) : '/api/intel/fixes?limit=200';
  const resp = await fetch(url);
  const data = await resp.json();
  renderFixes(data.fixes || []);
}

function renderFixes(fixes) {
  if (!fixes.length) {
    document.getElementById('intel-content').innerHTML =
      '<div class="loading" style="color:var(--muted)">No fix patterns found yet. Run a profile refresh.</div>';
    return;
  }

  // Group by repo
  const byRepo = {};
  fixes.forEach(f => (byRepo[f.repo] = byRepo[f.repo]||[]).push(f));

  let html = '';
  for (const [repo, items] of Object.entries(byRepo).sort((a,b) => b[1].length - a[1].length)) {
    html += `<div style="margin-bottom:24px">
      <div style="font-size:13px;font-weight:700;color:#e2e8f0;padding:6px 0;border-bottom:1px solid var(--border);margin-bottom:8px;display:flex;align-items:center;gap:8px">
        ${repo}
        <span style="font-size:11px;color:#ef4444;background:rgba(239,68,68,0.1);padding:1px 7px;border-radius:4px">${items.length} fixes</span>
      </div>`;
    for (const f of items) {
      const agentCol = AGENT_COLORS[f.agent] || '#64748b';
      const icon = f.agent === 'claude-code' ? '🤖' : f.agent === 'cursor' ? '🖱️' : '👤';
      html += `<div style="display:flex;gap:10px;padding:8px;border-radius:6px;margin-bottom:4px;background:var(--surface2);border-left:3px solid #ef4444">
        <div style="flex:1;min-width:0">
          <div style="font-size:12px;font-weight:600;color:#f87171">${f.what_broke || f.commit_subject || '—'}</div>
          ${f.how_fixed ? `<div style="font-size:11px;color:#94a3b8;margin-top:2px">${f.how_fixed}</div>` : ''}
          <div style="display:flex;gap:8px;margin-top:4px;flex-wrap:wrap">
            <span style="font-size:10px;color:${agentCol}">${icon} ${f.agent || 'human'}${f.model ? ' · ' + f.model : ''}</span>
            ${f.pr_number ? `<span style="font-size:10px;color:#64748b">PR #${f.pr_number}</span>` : ''}
            ${f.days_to_fix != null ? `<span style="font-size:10px;color:#64748b">${f.days_to_fix}d to fix</span>` : ''}
            <span style="font-size:10px;color:#334155">${(f.date||f.author_date||'').slice(0,10)}</span>
          </div>
        </div>
      </div>`;
    }
    html += '</div>';
  }
  document.getElementById('intel-content').innerHTML = html;
}

async function loadRepoProfiles() {
  const resp = await fetch('/api/intel/profiles?active_only=false');
  const data = await resp.json();
  renderRepoProfiles(data.profiles || []);
}

function renderRepoProfiles(profiles) {
  if (!profiles.length) {
    document.getElementById('intel-content').innerHTML = `
      <div style="text-align:center;padding:40px;color:var(--muted)">
        <div style="font-size:32px;margin-bottom:12px">🔍</div>
        <div style="font-weight:600;margin-bottom:8px">No profiles built yet</div>
        <div style="font-size:12px">Click "↻ Profile Repos" to deep-analyse all repos from GitHub API.<br>Takes ~2 min for 100+ repos.</div>
      </div>`;
    return;
  }

  const sorted = [...profiles].sort((a,b) => (b.total_commits||0) - (a.total_commits||0));
  let html = `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:12px">`;

  for (const p of sorted) {
    const agentCol = AGENT_COLORS[p.primary_agent] || '#64748b';
    const agentIcon = p.primary_agent === 'claude-code' ? '🤖' : p.primary_agent === 'cursor' ? '🖱️' : p.primary_agent === 'mixed' ? '🔀' : '👤';
    const networks = JSON.parse(p.docker_networks||'[]');
    const connects = JSON.parse(p.connects_to||'[]');
    const badges = [
      p.has_ci ? '<span style="font-size:10px;background:rgba(34,197,94,0.1);color:#22c55e;padding:1px 6px;border-radius:3px">CI</span>' : '',
      p.has_tests ? '<span style="font-size:10px;background:rgba(59,130,246,0.1);color:#3b82f6;padding:1px 6px;border-radius:3px">Tests</span>' : '',
      p.has_docker ? '<span style="font-size:10px;background:rgba(168,85,247,0.1);color:#a855f7;padding:1px 6px;border-radius:3px">Docker</span>' : '',
      p.claude_md_exists ? '<span style="font-size:10px;background:rgba(245,158,11,0.1);color:#f59e0b;padding:1px 6px;border-radius:3px">CLAUDE.md</span>' : '',
      p.coderabbit_used ? '<span style="font-size:10px;background:rgba(6,182,212,0.1);color:#06b6d4;padding:1px 6px;border-radius:3px">CodeRabbit</span>' : '',
    ].filter(Boolean).join(' ');

    html += `<div style="background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px;border-left:3px solid ${agentCol}">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:8px">
        <div>
          <div style="font-weight:700;font-size:14px">${p.display_name||p.repo}</div>
          <div style="font-size:11px;color:var(--muted)">${p.language||''} · ${p.total_commits||0} commits · ${p.open_issues||0} open issues</div>
        </div>
        <span style="color:${agentCol};font-size:18px" title="${p.primary_agent}">${agentIcon}</span>
      </div>
      ${p.purpose ? `<div style="font-size:12px;color:#94a3b8;margin-bottom:6px">${p.purpose.slice(0,200)}</div>` : ''}
      ${p.what_it_does_not_do ? `<div style="font-size:11px;color:#64748b;border-left:2px solid #ef4444;padding-left:8px;margin-bottom:6px">
        <span style="color:#ef4444;font-weight:600">Doesn't: </span>${p.what_it_does_not_do.slice(0,150)}</div>` : ''}
      <div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:8px">${badges}</div>
      ${networks.length ? `<div style="font-size:10px;color:#a855f7;margin-bottom:4px">🔗 ${networks.join(', ')}</div>` : ''}
      ${connects.length ? `<div style="font-size:10px;color:#64748b">Talks to: ${connects.join(', ')}</div>` : ''}
      ${p.public_url ? `<div style="margin-top:6px"><a href="${p.public_url}" target="_blank" style="font-size:11px;color:#3b82f6;text-decoration:none">${p.public_url}</a></div>` : ''}
      ${p.claude_model ? `<div style="font-size:10px;color:#a855f7;margin-top:4px">🤖 ${p.claude_model}</div>` : ''}
      <div id="plans-for-${p.repo}" style="margin-top:10px;border-top:1px solid var(--border);padding-top:8px">
        <span style="font-size:10px;color:var(--muted)">Loading plans…</span>
      </div>
    </div>`;
  }
  html += '</div>';
  document.getElementById('intel-content').innerHTML = html;

  // Lazy-load plan docs for each repo card
  sorted.forEach(p => loadPlansForRepo(p.repo));
}

async function loadPlansForRepo(repo) {
  const el = document.getElementById('plans-for-' + repo);
  if (!el) return;
  const docs = await fetch('/api/mdops/repo/' + encodeURIComponent(repo))
    .then(r => r.json()).catch(() => []);

  if (!docs.length) {
    el.innerHTML = '<span style="font-size:10px;color:#334155">No .md plans indexed for this repo</span>';
    return;
  }

  const plans = docs.filter(d => d.is_plan);
  const allDocs = docs;

  el.innerHTML = `
    <div style="font-size:10px;font-weight:600;color:#94a3b8;margin-bottom:5px;letter-spacing:0.05em">
      📄 PLANS & DOCS (${allDocs.length} indexed${plans.length ? ', ' + plans.length + ' plans' : ''})
    </div>
    <div style="display:flex;flex-direction:column;gap:3px">
      ${allDocs.slice(0,6).map(d => {
        const exists = d.file_exists ? '' : 'opacity:0.5;text-decoration:line-through;';
        const planBadge = d.is_plan
          ? '<span style="font-size:9px;background:rgba(245,158,11,0.15);color:#f59e0b;padding:0 4px;border-radius:3px;margin-left:4px">plan</span>'
          : '';
        return `<div onclick="openPlansDetail(${d.id})" style="cursor:pointer;display:flex;justify-content:space-between;align-items:center;
          padding:4px 6px;border-radius:4px;background:var(--surface2);${exists}"
          onmouseover="this.style.borderLeft='2px solid var(--blue)';this.style.paddingLeft='4px'"
          onmouseout="this.style.borderLeft='';this.style.paddingLeft='6px'">
          <div style="flex:1;min-width:0">
            <span style="font-size:11px;color:var(--text)">${d.filename}</span>
            ${planBadge}
            <div style="font-size:10px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:240px">${d.title||''}</div>
          </div>
          <span id="mini-grade-${d.id}" style="font-size:12px;font-weight:800;color:#334155;margin-left:8px;flex-shrink:0">…</span>
        </div>`;
      }).join('')}
      ${allDocs.length > 6 ? `<div style="font-size:10px;color:#334155;padding:2px 6px">+${allDocs.length - 6} more — search Plans tab</div>` : ''}
    </div>`;

  // Grade each plan doc (only plans, not all docs — keep it fast)
  plans.slice(0, 4).forEach(async d => {
    const grade = await fetch('/api/mdops/grade/' + d.id).then(r => r.json()).catch(() => null);
    if (!grade) return;
    const el2 = document.getElementById('mini-grade-' + d.id);
    if (el2) {
      const color = GRADE_COLORS[grade.grade] || '#64748b';
      el2.textContent = grade.grade;
      el2.style.color = color;
    }
  });
  // Non-plan docs get a dash
  allDocs.slice(0,6).filter(d => !d.is_plan).forEach(d => {
    const el2 = document.getElementById('mini-grade-' + d.id);
    if (el2) { el2.textContent = '—'; el2.style.color = '#334155'; }
  });
}

async function searchIntel() {
  const q = document.getElementById('intel-search').value;
  if (!q) { showIntelView(intelView); return; }
  const resp = await fetch('/api/intel/profiles?q=' + encodeURIComponent(q));
  const data = await resp.json();
  renderRepoProfiles(data.profiles || []);
}

async function triggerIntelRefresh() {
  const status = document.getElementById('intel-status');
  status.textContent = 'Profiling repos from GitHub...';
  await fetch('/api/intel/refresh', {method:'POST'});
  status.textContent = 'Running in background (~2 min). Reload tab after.';
  setTimeout(async () => { await loadRepoProfiles(); status.textContent = ''; }, 130000);
}

// ── Timeline tab ──────────────────────────────────────────────────────────
let timelineView = 'commits';  // 'commits' | 'prs'
let timelineLoaded = false;

function switchTimelineView(view) {
  timelineView = view;
  document.getElementById('btn-commits').style.background = view === 'commits' ? 'var(--blue)' : 'var(--surface2)';
  document.getElementById('btn-commits').style.color      = view === 'commits' ? '#fff' : 'var(--muted)';
  document.getElementById('btn-prs').style.background     = view === 'prs' ? 'var(--blue)' : 'var(--surface2)';
  document.getElementById('btn-prs').style.color          = view === 'prs' ? '#fff' : 'var(--muted)';
  loadTimeline();
}

async function initTimeline() {
  if (!allRepos) {
    // Populate repo dropdown from git repos
    const resp = await fetch('/api/git/repos');
    const data = await resp.json();
    allRepos = data.repos;
  }
  // Populate timeline repo dropdown
  const sel = document.getElementById('tl-repo');
  const sorted = [...(allRepos||[])].sort((a,b) => (b.commit_count||0) - (a.commit_count||0));
  sel.innerHTML = '<option value="">All repos</option>' +
    sorted.map(r => `<option value="${r.name}">${r.name} (${r.commit_count||0})</option>`).join('');

  loadTimeline();
}

async function loadTimeline() {
  const repo    = document.getElementById('tl-repo').value;
  const group   = document.getElementById('tl-group').value;
  const since   = document.getElementById('tl-since').value;
  const bots    = document.getElementById('tl-bots').checked;
  const container = document.getElementById('plotly-container');

  container.innerHTML = '<div class="loading"><div class="spinner"></div><br>Building charts...</div>';
  document.getElementById('tl-status').textContent = '';

  const params = new URLSearchParams();
  if (repo)  params.set('repo', repo);
  if (group) params.set('group_by', group);
  if (since) params.set('since', since);
  if (bots)  params.set('include_bots', 'true');

  const endpoint = timelineView === 'prs'
    ? `/api/timeline/prs?${new URLSearchParams({...(repo?{repo}:{})})}`
    : `/api/timeline/commits?${params}`;

  try {
    const resp = await fetch(endpoint);
    const html = await resp.text();
    // innerHTML silently drops <script> tags — use iframe srcdoc so scripts execute
    const iframe = document.createElement('iframe');
    iframe.style.cssText = 'width:100%;border:none;background:transparent;';
    iframe.style.height = '2000px';  // initial; resized after load
    container.innerHTML = '';
    container.appendChild(iframe);
    const doc = iframe.contentDocument || iframe.contentWindow.document;
    doc.open();
    doc.write(`<!DOCTYPE html><html><head>
      <script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></sc` + `ript>
      <style>
        body { margin:0; background:transparent; font-family:system-ui,sans-serif; }
        :root { --surface2:#252836; --border:#2e3148; --muted:#64748b; }
      </style>
      </head><body>${html}</body></html>`);
    doc.close();
    // Resize iframe to content after charts render
    iframe.onload = () => {
      try {
        const h = iframe.contentDocument.body.scrollHeight;
        iframe.style.height = (h + 40) + 'px';
      } catch(e) {}
    };
    setTimeout(() => {
      try {
        const h = iframe.contentDocument.body.scrollHeight;
        if (h > 100) iframe.style.height = (h + 40) + 'px';
      } catch(e) {}
    }, 1500);
  } catch(e) {
    container.innerHTML = `<div class="loading" style="color:#ef4444">Error: ${e.message}</div>`;
  }
}

async function triggerPRRefresh() {
  const status = document.getElementById('tl-status');
  status.textContent = 'Fetching PRs from GitHub...';
  await fetch('/api/timeline/refresh-prs', {method: 'POST'});
  status.textContent = 'PR fetch running in background (~2 min). Reload timeline after.';
}

// ── Git history tab ───────────────────────────────────────────────────────
let allCommits = null;       // currently loaded commits (for selected repo or search)
let allRepos = null;         // full repo list from /api/git/repos
let gitStatsData = null;
let currentRepoFilter = '';  // which repo is selected — drives per-repo fetch

async function loadGitHistory() {
  try {
    // Load stats + full repo list in parallel (both are fast from SQLite)
    const [statsResp, reposResp] = await Promise.all([
      fetch('/api/git/stats'),
      fetch('/api/git/repos'),
    ]);
    gitStatsData = await statsResp.json();
    const reposData = await reposResp.json();
    allRepos = reposData.repos;

    renderGitStats(gitStatsData);
    populateRepoFilter();

    const badge = document.getElementById('git-count-badge');
    if (badge) badge.textContent = `(${gitStatsData.total_commits.toLocaleString()})`;

    // Load all commits initially (no repo filter)
    await loadCommits('');

    if (gitStatsData.total_commits === 0) {
      document.getElementById('git-refresh-status').textContent = 'Fetching from GitHub...';
      triggerGitRefresh();
    }
  } catch(e) {
    document.getElementById('git-commits-container').innerHTML =
      `<div class="loading" style="color:#ef4444">Error: ${e.message}</div>`;
  }
}

async function loadCommits(repo) {
  currentRepoFilter = repo;
  const url = repo
    ? `/api/git/commits?limit=10000&repo=${encodeURIComponent(repo)}`
    : '/api/git/commits?limit=10000';
  const resp = await fetch(url);
  const data = await resp.json();
  allCommits = data.commits;
  renderCommits();
}

function renderGitStats(s) {
  if (!s) return;
  document.getElementById('git-stats').innerHTML = `
    <div class="stat"><div class="num" style="color:#22c55e">${s.total_commits.toLocaleString()}</div><div class="lbl">Total Commits</div></div>
    <div class="stat"><div class="num" style="color:#3b82f6">${s.total_repos}</div><div class="lbl">Repos Tracked</div></div>
    <div class="stat"><div class="num" style="color:#a855f7">${s.commits_last_7d}</div><div class="lbl">Last 7 Days</div></div>
    <div class="stat"><div class="num" style="color:#f59e0b">${s.commits_last_30d}</div><div class="lbl">Last 30 Days</div></div>
    <div class="stat" style="min-width:180px">
      <div style="font-size:11px;color:var(--muted)">Top Repos</div>
      ${(s.top_repos||[]).slice(0,3).map(r =>
        `<div style="font-size:11px;margin-top:2px"><span style="color:#e2e8f0">${r.repo}</span> <span style="color:#64748b">${r.cnt}</span></div>`
      ).join('')}
    </div>
    <div class="stat" style="min-width:160px">
      <div style="font-size:11px;color:var(--muted)">Authors</div>
      ${(s.by_author||[]).slice(0,3).map(a =>
        `<div style="font-size:11px;margin-top:2px"><span style="color:#e2e8f0">${a.author_name}</span> <span style="color:#64748b">${a.cnt}</span></div>`
      ).join('')}
    </div>
    <div class="stat"><div style="font-size:10px;color:var(--muted)">Last synced</div>
      <div style="font-size:11px;color:#64748b;margin-top:4px">${s.last_fetched ? new Date(s.last_fetched).toLocaleString() : 'Never'}</div>
      <div style="font-size:10px;margin-top:2px;color:${s.cache_fresh ? '#22c55e':'#f59e0b'}">${s.cache_fresh ? '✓ Fresh':'↻ Stale'}</div>
    </div>
  `;
}

function populateRepoFilter() {
  if (!allRepos) return;
  const sel = document.getElementById('git-repo-filter');
  // Sort: repos with most commits first
  const sorted = [...allRepos].sort((a, b) => (b.commit_count || 0) - (a.commit_count || 0));
  sel.innerHTML = `<option value="">All repos (${allRepos.length})</option>` +
    sorted.map(r => {
      const cnt = r.commit_count ? ` (${r.commit_count})` : '';
      const lang = r.language ? ` · ${r.language}` : '';
      return `<option value="${r.name}">${r.name}${cnt}${lang}</option>`;
    }).join('');
}

function renderCommits() {
  if (!allCommits) return;
  const search = document.getElementById('git-search').value.toLowerCase();
  // Repo filter is handled server-side by loadCommits — only apply text search here
  let commits = allCommits;

  if (search) commits = commits.filter(c =>
    [c.message, c.repo, c.author_name, c.sha].some(f => (f||'').toLowerCase().includes(search))
  );

  if (!commits.length) {
    document.getElementById('git-commits-container').innerHTML =
      '<div class="loading">No commits match.</div>';
    return;
  }

  // Group by repo
  const byRepo = {};
  commits.forEach(c => (byRepo[c.repo] = byRepo[c.repo] || []).push(c));

  let html = '';
  for (const [repo, repoComs] of Object.entries(byRepo).sort((a,b) => {
    const aDate = a[1][0].author_date || '';
    const bDate = b[1][0].author_date || '';
    return bDate.localeCompare(aDate);
  })) {
    const owner = repoComs[0].owner;
    html += `<div style="margin-bottom:20px">
      <div style="display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid var(--border);margin-bottom:8px">
        <span style="font-weight:700;font-size:13px">${repo}</span>
        <span style="font-size:11px;color:var(--muted)">${owner}</span>
        <span style="font-size:11px;color:var(--blue);margin-left:auto">${repoComs.length} commits</span>
        <a href="https://github.com/${owner}/${repo}" target="_blank"
           style="font-size:11px;color:var(--purple);text-decoration:none">⎇ GitHub</a>
      </div>`;

    for (const c of repoComs.slice(0, 50)) {
      const msg = c.message || '';
      const subject = msg.split('\\n')[0];
      const body = msg.split('\\n').slice(1).join(' ').trim();
      const date = c.author_date ? new Date(c.author_date).toLocaleDateString() : '';
      const typeMatch = subject.match(/^(feat|fix|chore|docs|refactor|test|style|perf|ci|build)(\\([^)]*\\))?:/);
      const typeColors = {feat:'#22c55e',fix:'#ef4444',chore:'#64748b',docs:'#3b82f6',refactor:'#a855f7',test:'#f59e0b',ci:'#06b6d4',build:'#94a3b8',perf:'#f59e0b',style:'#94a3b8'};
      const typeColor = typeMatch ? (typeColors[typeMatch[1]] || '#94a3b8') : '#94a3b8';
      const typeLabel = typeMatch ? typeMatch[0] : '';
      const subjectClean = typeMatch ? subject.slice(typeMatch[0].length).trim() : subject;

      const adds = c.additions || 0;
      const dels = c.deletions || 0;
      html += `<div style="display:flex;align-items:flex-start;gap:10px;padding:6px 8px;border-radius:6px;margin-bottom:2px;background:var(--surface2)">
        <span style="font-family:monospace;font-size:10px;color:var(--muted);padding-top:2px;white-space:nowrap">
          <a href="${c.url||'#'}" target="_blank" style="color:inherit;text-decoration:none">${(c.sha||'').slice(0,7)}</a>
        </span>
        <div style="flex:1;min-width:0">
          <div style="font-size:12px;color:#e2e8f0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${subject}">
            ${typeLabel ? `<span style="color:${typeColor};font-weight:700">${typeLabel}</span> ` : ''}${subjectClean}
          </div>
          ${body ? `<div style="font-size:11px;color:#64748b;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${body.slice(0,120)}</div>` : ''}
        </div>
        <div style="display:flex;gap:6px;align-items:center;white-space:nowrap;flex-shrink:0">
          ${adds ? `<span style="font-size:10px;color:#22c55e">+${adds}</span>` : ''}
          ${dels ? `<span style="font-size:10px;color:#ef4444">-${dels}</span>` : ''}
          <span style="font-size:10px;color:#64748b">${c.author_name||''}</span>
          <span style="font-size:10px;color:#334155">${date}</span>
        </div>
      </div>`;
    }
    if (repoComs.length > 50) {
      html += `<div style="font-size:11px;color:var(--muted);padding:4px 8px">...and ${repoComs.length - 50} more</div>`;
    }
    html += '</div>';
  }

  document.getElementById('git-commits-container').innerHTML = html;
}

async function triggerGitRefresh() {
  const status = document.getElementById('git-refresh-status');
  status.textContent = 'Refreshing from GitHub...';
  try {
    await fetch('/api/git/refresh', {method: 'POST'});
    status.textContent = 'Running in background — reload in ~30s';
    setTimeout(async () => {
      await loadGitHistory();
      status.textContent = '';
    }, 35000);
  } catch(e) {
    status.textContent = 'Error: ' + e.message;
  }
}

// ── Status helpers ────────────────────────────────────────────────────────
function statusClass(s) {
  if (s.error === 'timeout') return 'timeout';
  if (s.error) return 'down';
  if (!s.reachable) return 'down';
  if (s.redirect_is_auth) return 'auth';
  return 'up';
}
function badgeText(s) {
  if (s.error === 'timeout') return 'TIMEOUT';
  if (s.error) return 'ERROR';
  if (!s.reachable) return `DOWN ${s.status_code ? '('+s.status_code+')' : ''}`;
  if (s.redirect_is_auth) return `AUTH WALL (${s.status_code})`;
  return `UP (${s.status_code})`;
}
function msClass(ms) {
  if (!ms) return '';
  if (ms < 500) return 'fast';
  if (ms < 2000) return 'slow';
  return 'very-slow';
}

// ── Services tab ──────────────────────────────────────────────────────────
function setFilter(cat, btn) {
  activeFilter = cat;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderServices();
}

function renderServices() {
  if (!allData) return;
  const grid = document.getElementById('grid');
  const search = document.getElementById('search').value.toLowerCase();

  let services = allData.services;
  if (activeFilter === 'problems') {
    services = services.filter(s => !s.reachable || s.error);
  } else if (activeFilter !== 'all') {
    services = services.filter(s => s.category === activeFilter);
  }
  if (search) {
    services = services.filter(s =>
      [s.name, s.description, s.what_it_does, s.url, s.container_name || ''].some(f => f.toLowerCase().includes(search))
    );
  }

  if (!services.length) {
    grid.innerHTML = '<div id="no-results">No services match.</div>';
    return;
  }

  const bycat = {};
  services.forEach(s => (bycat[s.category] = bycat[s.category] || []).push(s));
  const catOrder = ['terry','pete','ai','monitoring','infrastructure','voice','sites','tools'];
  const ordered = catOrder.filter(c => bycat[c]).concat(Object.keys(bycat).filter(c => !catOrder.includes(c)));

  let html = '';
  for (const cat of ordered) {
    const items = bycat[cat];
    const up = items.filter(s => s.reachable && !s.error).length;
    const col = up === items.length ? '#22c55e' : up === 0 ? '#ef4444' : '#f59e0b';
    html += `<div class="section-header">
      <h2>${items[0].category_label}</h2>
      <span class="count" style="color:${col}">${up}/${items.length} up</span>
    </div>`;

    for (const s of items) {
      const cls = statusClass(s);
      html += `<div class="card ${cls}">
        <div class="card-header">
          <div>
            <div class="card-name">${s.name}</div>
            <div class="card-cat">${s.category_label}</div>
          </div>
          <span class="badge ${cls}">${badgeText(s)}</span>
        </div>
        <div class="card-desc">${s.description}</div>
        <div class="card-detail">${s.what_it_does}</div>
        <div class="card-meta">
          ${s.has_docs ? `<span class="pill docs"><a href="${s.docs_url}" target="_blank">📖 docs</a></span>` : ''}
          ${s.has_health ? `<span class="pill health">✓ ${s.health_status}</span>` : ''}
          ${s.repo ? `<span class="pill repo"><a href="https://github.com/${s.repo}" target="_blank">⎇ ${s.repo.split('/')[1]}</a></span>` : ''}
          ${s.route_count ? `<span class="pill routes" onclick="viewRoutesFor('${s.name}')">🔌 ${s.route_count} routes</span>` : ''}
          ${s.response_time_ms ? `<span class="pill ${msClass(s.response_time_ms)}">${s.response_time_ms}ms</span>` : ''}
          ${s.server_header ? `<span class="pill">${s.server_header}</span>` : ''}
          ${(s.docker_networks||[]).map(n => `<span class="pill" style="color:#a855f7;border-color:rgba(168,85,247,0.3);background:rgba(168,85,247,0.08)">🔗 ${n.replace('-network','')}</span>`).join('')}
          ${s.container_name ? `<span class="pill" style="font-size:10px">📦 ${s.container_name}</span>` : ''}
        </div>
        ${s.redirect_is_auth ? `<div class="card-desc" style="color:#06b6d4">→ Auth wall (Clerk/login)</div>` : ''}
        ${s.error && s.error !== 'timeout' ? `<div class="card-error">Error: ${s.error}</div>` : ''}
        ${(s.connects_to||[]).length ? `<div class="card-desc" style="color:#64748b;font-size:11px">Talks to: ${s.connects_to.join(', ')}</div>` : ''}
        <div class="card-url"><a href="${s.url}" target="_blank">${s.url}</a></div>
      </div>`;
    }
  }
  grid.innerHTML = html;
}

function updateSummary(data) {
  document.getElementById('summary').innerHTML = `
    <div class="stat"><div class="num" style="color:#22c55e">${data.up}</div><div class="lbl">Up</div></div>
    <div class="stat"><div class="num" style="color:#ef4444">${data.down}</div><div class="lbl">Down / Error</div></div>
    <div class="stat"><div class="num" style="color:#06b6d4">${data.auth_wall}</div><div class="lbl">Auth Wall</div></div>
    <div class="stat"><div class="num" style="color:#3b82f6">${data.with_docs}</div><div class="lbl">Have Docs</div></div>
    <div class="stat"><div class="num" style="color:#f59e0b">${data.total_api_routes || 0}</div><div class="lbl">API Routes</div></div>
    <div class="stat"><div class="num" style="color:#94a3b8">${data.total}</div><div class="lbl">Total</div></div>
  `;
}

// ── Routes tab ────────────────────────────────────────────────────────────
function viewRoutesFor(serviceName) {
  showTab('routes', document.querySelectorAll('.tab')[1]);
  if (allRoutes) {
    document.getElementById('route-search').value = serviceName;
    renderRoutes();
  } else {
    loadRoutes().then(() => {
      document.getElementById('route-search').value = serviceName;
      renderRoutes();
    });
  }
}

async function loadRoutes() {
  try {
    const resp = await fetch('/api/routes');
    const data = await resp.json();
    allRoutes = data.routes;
    document.getElementById('route-count-badge').textContent = `(${data.total})`;
    renderRoutes();
  } catch(e) {
    document.getElementById('routes-container').innerHTML = `<div class="loading" style="color:#ef4444">Error: ${e.message}</div>`;
  }
}

function renderRoutes() {
  if (!allRoutes) return;
  const search = document.getElementById('route-search').value.toLowerCase();
  let routes = allRoutes;
  if (search) {
    routes = routes.filter(r =>
      [r.path, r.method, r.service_name, r.summary || '', r.description || '',
       r.business_summary || '', r.container_name || ''].some(f =>
        f.toLowerCase().includes(search)
      )
    );
  }

  if (!routes.length) {
    document.getElementById('routes-container').innerHTML = '<div class="loading">No routes match.</div>';
    return;
  }

  let html = `<table class="route-table">
    <thead><tr>
      <th>Service / Container</th><th>Method</th><th>Path</th>
      <th>What It Does (Plain English)</th><th>Technical Summary</th><th>Tags</th>
    </tr></thead><tbody>`;

  for (const r of routes) {
    const tags = Array.isArray(r.tags) ? r.tags : [];
    const tagHtml = tags.map(t => `<span class="tag-chip">${t}</span>`).join('');
    const biz = r.business_summary || r.summary || r.description || '';
    const tech = (r.summary && r.business_summary && r.summary !== r.business_summary) ? r.summary : '';
    const container = r.container_name ? `<div style="color:#64748b;font-size:10px;margin-top:2px">📦 ${r.container_name}</div>` : '';
    html += `<tr>
      <td class="route-svc">${r.service_name}${container}</td>
      <td><span class="method ${r.method}">${r.method}</span></td>
      <td class="route-path">${r.path}</td>
      <td class="route-summary" style="color:#e2e8f0;max-width:320px">${biz}</td>
      <td class="route-summary" style="color:#64748b;font-size:11px;max-width:200px">${tech}</td>
      <td><div class="route-tags">${tagHtml}</div></td>
    </tr>`;
  }
  html += '</tbody></table>';
  document.getElementById('routes-container').innerHTML = html;
}

// ── Data loading ──────────────────────────────────────────────────────────
async function load(force = false) {
  const btn = document.getElementById('refresh-btn');
  btn.disabled = true; btn.textContent = 'Checking...';
  try {
    const resp = await fetch(force ? '/api/status?force=true' : '/api/status');
    const data = await resp.json();
    if (data.running && !data.services.length) {
      setTimeout(() => load(), 2000);
      return;
    }
    allData = data;
    updateSummary(data);
    const ts = data.checked_at ? new Date(data.checked_at).toLocaleTimeString() : '—';
    document.getElementById('checked-at').textContent = `Checked: ${ts}`;
    renderServices();
    if (data.total_api_routes) {
      document.getElementById('route-count-badge').textContent = `(${data.total_api_routes})`;
    }
  } catch(e) {
    document.getElementById('grid').innerHTML = `<div class="loading" style="color:#ef4444">Error: ${e.message}</div>`;
  } finally {
    btn.disabled = false; btn.textContent = 'Refresh';
  }
}

function refresh() { load(true); }

load();
setInterval(() => load(false), 90000);

// ── Plans & Docs tab ──────────────────────────────────────────────────────
let plansInited = false;

const GRADE_COLORS = { A:'#22c55e', B:'#84cc16', C:'#f59e0b', D:'#f97316', F:'#ef4444' };

async function initPlans() {
  if (plansInited) return;
  plansInited = true;
  const stats = await fetch('/api/mdops/stats').then(r => r.json()).catch(() => ({}));
  const strip = document.getElementById('plans-stats-strip');
  strip.innerHTML = [
    ['Total docs', stats.total_docs ?? '…'],
    ['Plan/spec docs', stats.plan_docs ?? '…'],
    ['Git-tracked', stats.with_git ?? '…'],
    ['Projects', stats.projects ?? '…'],
  ].map(([label, val]) => `
    <div class="stat">
      <div style="font-size:22px;font-weight:800;color:#e2e8f0">${val}</div>
      <div style="font-size:11px;color:var(--muted)">${label}</div>
    </div>`).join('');
  document.getElementById('plans-count-badge').textContent = stats.total_docs ? `(${stats.total_docs})` : '';
}

let plansSearchTimer = null;
function plansSearch() {
  clearTimeout(plansSearchTimer);
  plansSearchTimer = setTimeout(_doPlansSearch, 300);
}

async function _doPlansSearch() {
  const q = document.getElementById('plans-search').value.trim();
  if (!q) { document.getElementById('plans-content').innerHTML = '<div style="color:var(--muted);font-size:13px;padding:20px 0">Type to search…</div>'; return; }
  const gitOnly = document.getElementById('plans-git-only').checked;
  document.getElementById('plans-status').textContent = 'Searching…';
  const results = await fetch(`/api/mdops/search?q=${encodeURIComponent(q)}&limit=60&git_only=${gitOnly}`).then(r => r.json()).catch(() => []);
  document.getElementById('plans-status').textContent = `${results.length} results`;
  renderPlanResults(results);
}

async function plansLoadProjects() {
  document.getElementById('plans-status').textContent = 'Loading…';
  const projects = await fetch('/api/mdops/projects?limit=120').then(r => r.json()).catch(() => []);
  document.getElementById('plans-status').textContent = `${projects.length} projects`;
  const content = document.getElementById('plans-content');
  content.innerHTML = `
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px">
      ${projects.map(p => `
        <div onclick="plansSearchProject('${(p.name||'').replace(/'/g,"\\'")}',event)"
          style="background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:12px;cursor:pointer;transition:border-color 0.15s"
          onmouseover="this.style.borderColor='var(--blue)'" onmouseout="this.style.borderColor='var(--border)'">
          <div style="font-weight:600;font-size:13px;color:var(--text);margin-bottom:4px">${p.name||'(unnamed)'}</div>
          <div style="font-size:11px;color:var(--muted);margin-bottom:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${p.path||''}</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <span style="font-size:11px;color:#64748b">${p.doc_count||p.markdown_count||0} docs</span>
            ${p.is_git_repo ? '<span style="font-size:10px;background:#1e3a5f;color:#60a5fa;padding:1px 6px;border-radius:4px">git</span>' : ''}
            ${p.has_api ? '<span style="font-size:10px;background:#14532d;color:#4ade80;padding:1px 6px;border-radius:4px">api</span>' : ''}
            ${p.has_docker_compose ? '<span style="font-size:10px;background:#3b1f5e;color:#c084fc;padding:1px 6px;border-radius:4px">docker</span>' : ''}
          </div>
        </div>`).join('')}
    </div>`;
}

function plansSearchProject(name, e) {
  document.getElementById('plans-search').value = name;
  _doPlansSearch();
}

function renderPlanResults(results) {
  const content = document.getElementById('plans-content');
  if (!results.length) { content.innerHTML = '<div style="color:var(--muted);padding:20px 0">No results.</div>'; return; }
  content.innerHTML = `
    <table style="width:100%;border-collapse:collapse;font-size:12px">
      <thead>
        <tr style="color:var(--muted);text-align:left;border-bottom:1px solid var(--border)">
          <th style="padding:6px 10px">Doc</th>
          <th style="padding:6px 10px">Project</th>
          <th style="padding:6px 10px">Words</th>
          <th style="padding:6px 10px">Git</th>
          <th style="padding:6px 10px">Updated</th>
          <th style="padding:6px 10px">Grade</th>
        </tr>
      </thead>
      <tbody>
        ${results.map(r => `
          <tr onclick="openPlansDetail(${r.id})"
            style="border-bottom:1px solid var(--border);cursor:pointer"
            onmouseover="this.style.background='var(--surface2)'" onmouseout="this.style.background=''">
            <td style="padding:7px 10px">
              <div style="font-weight:600;color:var(--text)">${r.filename||''}</div>
              <div style="color:var(--muted);font-size:11px;max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${r.title||''}</div>
            </td>
            <td style="padding:7px 10px;color:var(--muted)">${r.project||''}</td>
            <td style="padding:7px 10px;color:var(--muted)">${r.word_count||''}</td>
            <td style="padding:7px 10px">${r.git_root ? '<span style="color:#60a5fa;font-size:11px">✓ git</span>' : '<span style="color:var(--muted);font-size:11px">—</span>'}</td>
            <td style="padding:7px 10px;color:var(--muted);white-space:nowrap">${(r.file_updated_at||'').split('T')[0]||'—'}</td>
            <td style="padding:7px 10px" id="grade-${r.id}"><span style="color:var(--muted);font-size:11px">…</span></td>
          </tr>`).join('')}
      </tbody>
    </table>`;
  // Lazy-load grades for git-tracked docs
  results.filter(r => r.git_root).forEach(r => loadGrade(r.id));
}

async function loadGrade(id) {
  const grade = await fetch(`/api/mdops/grade/${id}`).then(r => r.json()).catch(() => null);
  if (!grade) return;
  const cell = document.getElementById(`grade-${id}`);
  if (cell) {
    const color = GRADE_COLORS[grade.grade] || '#64748b';
    cell.innerHTML = `<span style="font-weight:800;color:${color};font-size:14px">${grade.grade}</span>
      <span style="color:var(--muted);font-size:10px;margin-left:4px">${grade.score}pt</span>`;
  }
}

async function openPlansDetail(id) {
  document.getElementById('plans-detail').style.display = '';
  document.getElementById('plans-detail-title').textContent = 'Loading…';
  document.getElementById('plans-detail-body').innerHTML = '<div class="loading"><div class="spinner"></div></div>';

  const [doc, grade] = await Promise.all([
    fetch(`/api/mdops/doc/${id}`).then(r => r.json()).catch(() => ({})),
    fetch(`/api/mdops/grade/${id}`).then(r => r.json()).catch(() => ({})),
  ]);

  document.getElementById('plans-detail-title').textContent = doc.filename || '(unknown)';

  const gradeColor = GRADE_COLORS[grade.grade] || '#64748b';
  const commits = (grade.recent_commits || []).slice(0,8);
  const breakdown = grade.grade_breakdown || {};

  document.getElementById('plans-detail-body').innerHTML = `
    <!-- Grade panel -->
    <div style="background:var(--surface2);border-radius:8px;padding:14px;margin-bottom:16px;border:1px solid var(--border)">
      <div style="display:flex;align-items:center;gap:16px;margin-bottom:12px">
        <div style="font-size:48px;font-weight:900;color:${gradeColor};line-height:1">${grade.grade||'?'}</div>
        <div>
          <div style="font-size:12px;color:var(--muted)">Score: ${grade.score||0} / 13</div>
          <div style="font-size:11px;color:var(--muted);margin-top:4px">
            ${grade.github_repo ? `<a href="https://github.com/${grade.github_repo}" target="_blank" style="color:#60a5fa">${grade.github_repo}</a>` : 'No GitHub remote detected'}
          </div>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;font-size:11px">
        ${Object.entries(breakdown).map(([k,v]) => `
          <div style="background:var(--surface);border-radius:6px;padding:7px 10px;border:1px solid var(--border)">
            <div style="color:${v > 0 ? '#22c55e' : '#64748b'};font-weight:700">${v > 0 ? '+'+v : '0'}</div>
            <div style="color:var(--muted)">${k.replace(/_/g,' ')}</div>
          </div>`).join('')}
      </div>
    </div>

    <!-- Metadata -->
    <div style="font-size:11px;color:var(--muted);margin-bottom:12px;display:flex;flex-direction:column;gap:3px">
      <div><strong>Path:</strong> ${doc.full_path||'—'}</div>
      <div><strong>Words:</strong> ${doc.word_count||'—'} &nbsp; <strong>Git root:</strong> ${grade.git_root||'none'}</div>
      <div><strong>PRs in repo:</strong> ${grade.pr_count||0} &nbsp;
           <strong>PR numbers found:</strong> ${(grade.pr_numbers||[]).map(n=>`<a href="https://github.com/${grade.github_repo}/pull/${n}" target="_blank" style="color:#60a5fa">#${n}</a>`).join(', ')||'none'}</div>
    </div>

    <!-- Commits -->
    ${commits.length ? `
    <div style="margin-bottom:16px">
      <div style="font-size:12px;font-weight:600;color:var(--text);margin-bottom:8px">Git commits touching this file</div>
      <div style="display:flex;flex-direction:column;gap:4px">
        ${commits.map(c => `
          <div style="background:var(--surface2);border-radius:6px;padding:8px 10px;border:1px solid var(--border);font-size:11px">
            <div style="display:flex;gap:8px;align-items:center">
              <code style="color:var(--muted)">${c.sha}</code>
              <span style="color:var(--muted)">${c.date}</span>
              ${c.pr_number ? `<a href="https://github.com/${grade.github_repo}/pull/${c.pr_number}" target="_blank" style="color:#60a5fa;font-size:10px">#${c.pr_number}</a>` : ''}
              <span style="color:${c.is_bot ? '#64748b' : '#22c55e'};font-size:10px">${c.is_bot ? 'bot' : c.author}</span>
            </div>
            <div style="color:var(--text);margin-top:3px">${c.subject}</div>
          </div>`).join('')}
      </div>
    </div>` : '<div style="color:var(--muted);font-size:12px;margin-bottom:16px">No git history for this file.</div>'}

    <!-- Doc content preview -->
    ${doc.content ? `
    <div>
      <div style="font-size:12px;font-weight:600;color:var(--text);margin-bottom:8px">Document content</div>
      <pre style="background:var(--surface2);border:1px solid var(--border);border-radius:6px;padding:12px;
        font-size:11px;color:var(--muted);overflow-x:auto;white-space:pre-wrap;max-height:400px;overflow-y:auto">${doc.content.replace(/</g,'&lt;').replace(/>/g,'&gt;')}</pre>
    </div>` : ''}
  `;
}

function closePlansDetail() {
  document.getElementById('plans-detail').style.display = 'none';
}
</script>
</body>
</html>
"""
