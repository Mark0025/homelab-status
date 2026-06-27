"""FastAPI web server — live dashboard of homelab endpoint status."""

import asyncio
from datetime import datetime

from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
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
    refresh_issues, get_issue_stats,
)
from .project_intel import (
    enrich_commits_with_agents, get_agent_stats, get_all_profiles,
    get_project_profile, extract_fix_patterns, detect_refixes, refix_mermaid,
    refixes_with_plans, code_audit, capability_record, search_profiles,
    refresh_all_profiles, _profile_running as _intel_running,
)
from .services import CATEGORY_LABELS, SERVICES
from .mdops import (
    doc_stats, docs_for_repo, get_doc, grade_doc, plan_reality,
    list_projects, search_docs,
)
from .journey import (
    get_chapters, get_episodes, get_episode_questions, get_journey_stats,
    scaffold_episodes, update_episode, save_answer, update_question,
    get_personas, clone_questions_for_persona, refresh_all_deps, scan_repo_deps,
    get_episode_deps, generate_persona_questions, get_episode_script, PERSONA_STYLES,
    elevenlabs_tts, persona_voice_id, load_env_key,
)
from .enricher import enrich_all_episodes, enrich_one_episode
from .infra import (
    runtime_summary, container_runtime, runtime_for_repo,
    npm_proxies, friendly_urls_for, network_alignment,
)
from .logging_config import configure_logging

# Configure logging at import time so the uvicorn container gets a structured,
# level-controlled loguru sink (not loguru's unconfigured default). Issue #22.
configure_logging()

api = FastAPI(title="Homelab Status", docs_url=None, redoc_url=None)

# Frontend served from real files (issue #25) — was a ~1,800-line _HTML string.
_HERE = Path(__file__).parent
api.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")
templates = Jinja2Templates(directory=str(_HERE / "templates"))

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


@api.post("/api/issues/refresh")
async def issues_refresh():
    """Ingest GitHub issues (the problem side of the arc) for all repos."""
    asyncio.create_task(refresh_issues())
    return JSONResponse({"status": "issue_refresh_started"})


@api.get("/api/issues/stats")
async def issues_stats():
    return JSONResponse(get_issue_stats())


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


@api.get("/api/intel/refixes")
async def intel_refixes(repo: str | None = Query(None), limit: int = Query(100)):
    """Re-fixes (#13 Layer A): fix pairs where the earlier fix didn't hold,
    each annotated with the repo's plan docs (#13 PR 3) — was this area planned?"""
    refixes = refixes_with_plans(repo=repo, limit=limit)
    planned = sum(1 for r in refixes if r.get("had_plan"))
    return JSONResponse({"total": len(refixes), "planned_but_broke": planned, "refixes": refixes})


@api.get("/api/intel/refixes/mermaid")
async def intel_refixes_mermaid(repo: str | None = Query(None), limit: int = Query(12)):
    """Re-fixes as Mermaid graph syntax (#13 PR 2) — the browser renders it."""
    return JSONResponse({"diagram": refix_mermaid(repo=repo, limit=limit)})


@api.get("/api/intel/audit/{owner}/{repo}")
async def intel_code_audit(owner: str, repo: str):
    """Code audit (#13): REAL deps + REAL routes from the source, not metadata."""
    return JSONResponse(await code_audit(owner, repo))


@api.get("/api/infra/summary")
async def infra_summary():
    """The diagram server's live homelab overview, consumed (#14)."""
    return JSONResponse(await runtime_summary())


@api.get("/api/infra/network-alignment")
async def infra_network_alignment():
    """Config-correctness: for each NPM friendly URL, is its forward_host on a
    network the proxy can reach? MISALIGNED = 'Connection failed' despite a
    healthy container. (Mark's docker-networking alignment model.)"""
    rows = await network_alignment()
    bad = [r for r in rows if r["status"] == "MISALIGNED"]
    return JSONResponse({"total": len(rows), "misaligned": len(bad),
                         "alignment": rows})


@api.get("/api/registry/{owner}/{repo}")
async def registry_record(owner: str, repo: str):
    """Capability record (#13 keystone): one machine-readable record an AGENT
    routes on — what this repo does, exposes, is built with, and is it callable."""
    return JSONResponse(await capability_record(owner, repo))


@api.get("/api/intel/built/{owner}/{repo}")
async def intel_built(owner: str, repo: str):
    """The full picture of one repo ('employee'): what the CODE declares
    (code-audit), whether it's DEPLOYED & running (diagram runtime), and its
    FRIENDLY URLs + auth (NPM proxy map). Everything the app already knows,
    joined. (#13 + #14)."""
    audit = await code_audit(owner, repo)
    cmap = await container_runtime()
    runtime = runtime_for_repo(cmap, repo)
    proxies = await npm_proxies()
    containers = runtime["containers"] if runtime else []
    friendly = friendly_urls_for(proxies, repo, containers)
    return JSONResponse({
        "repo": repo,
        "code": {"deps": audit["deps"], "routes": audit["routes"],
                 "dep_source": audit["dep_source"], "route_sources": audit["route_sources"]},
        "runtime": runtime,                     # None if no matching running container
        "deployed": runtime is not None,
        "running": bool(runtime and runtime.get("health") == "healthy"),
        "container_count": runtime.get("container_count") if runtime else 0,
        "friendly_urls": friendly,              # the NPM friendly-name layer
    })


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


@api.get("/api/mdops/reality/{doc_id}")
async def mdops_reality(doc_id: int):
    """Plan vs execution (#13): 'what was WORKING vs NOT' for this plan."""
    return JSONResponse(plan_reality(doc_id))


@api.get("/api/mdops/repo/{repo_name}")
async def mdops_repo_docs(repo_name: str):
    return JSONResponse(docs_for_repo(repo_name))


# ── Journey endpoints ─────────────────────────────────────────────────────────

@api.get("/api/journey/stats")
async def journey_stats():
    """High-level counts for the journey dashboard."""
    return JSONResponse(get_journey_stats())


@api.get("/api/journey/chapters")
async def journey_chapters():
    """All 5 eras with episode counts."""
    return JSONResponse({"chapters": get_chapters()})


@api.get("/api/journey/episodes")
async def journey_episodes(
    chapter: str | None = Query(None),
    status: str | None = Query(None),
):
    """Episodes filtered by chapter and/or status."""
    rows = get_episodes(chapter_name=chapter, status=status)
    return JSONResponse({"total": len(rows), "episodes": rows})


@api.get("/api/journey/episode/{episode_id}/questions")
async def journey_questions(episode_id: int, persona: str = Query("default")):
    """All Q&A for one episode, optionally filtered by interviewer persona."""
    rows = get_episode_questions(episode_id, persona=persona)
    personas = get_personas(episode_id)
    return JSONResponse({"total": len(rows), "questions": rows, "personas": personas})


@api.patch("/api/journey/episode/{episode_id}")
async def journey_update_episode(episode_id: int, payload: dict):
    """Update episode fields (status, audio_url, transcript, etc.)."""
    update_episode(episode_id, **payload)
    return JSONResponse({"ok": True})


@api.post("/api/journey/question/{question_id}/answer")
async def journey_save_answer(question_id: int, payload: dict):
    """Store Mark's answer for a question post-interview."""
    answer = payload.get("answer_text", "")
    save_answer(question_id, answer)
    return JSONResponse({"ok": True})


@api.post("/api/journey/scaffold")
async def journey_scaffold():
    """(Re-)generate episode + question scaffolding from journey_repos."""
    n = scaffold_episodes()
    return JSONResponse({"episodes_created": n})


@api.post("/api/journey/enrich")
async def journey_enrich(limit: int | None = Query(None)):
    """Replace generic template questions with specific ones built from real commit data."""
    result = enrich_all_episodes(limit=limit)
    return JSONResponse(result)


@api.post("/api/journey/episode/{episode_id}/enrich")
async def journey_enrich_one(episode_id: int):
    """Deep-dive enrich a single episode from its real commit history + PAI learnings."""
    import asyncio
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, enrich_one_episode, episode_id)
    return JSONResponse(result)


@api.patch("/api/journey/question/{question_id}")
async def journey_update_question(question_id: int, payload: dict):
    """Edit a question's text. Marks is_edited=1 so enricher won't overwrite it."""
    text = payload.get("question_text", "").strip()
    if not text:
        return JSONResponse({"error": "question_text required"}, status_code=400)
    update_question(question_id, text)
    return JSONResponse({"ok": True})


@api.get("/api/journey/episode/{episode_id}/personas")
async def journey_get_personas(episode_id: int):
    """List all interviewer personas that have questions for this episode."""
    return JSONResponse({"personas": get_personas(episode_id)})


@api.post("/api/journey/episode/{episode_id}/persona")
async def journey_create_persona(episode_id: int, payload: dict):
    """Clone the default questions into a new interviewer persona."""
    name = payload.get("name", "").strip().lower().replace(" ", "_")
    if not name or name == "default":
        return JSONResponse({"error": "name required and cannot be 'default'"}, status_code=400)
    n = clone_questions_for_persona(episode_id, name)
    return JSONResponse({"ok": True, "cloned": n, "persona": name})


@api.get("/api/journey/episode/{episode_id}/deps")
async def journey_episode_deps(episode_id: int):
    """Return package deps for the repo attached to this episode."""
    return JSONResponse(get_episode_deps(episode_id))


@api.post("/api/journey/deps/refresh")
async def journey_refresh_deps():
    """Scan all locally cloned repos for package files and store deps_snapshot."""
    result = refresh_all_deps()
    return JSONResponse(result)


@api.post("/api/journey/episode/{episode_id}/persona/generate")
async def journey_generate_persona(episode_id: int, payload: dict):
    """
    Use Claude to rewrite questions in a named interviewer style.
    payload: {name: "gary_vee"} — name must be in PERSONA_STYLES or any custom string.
    """
    name = payload.get("name", "").strip().lower().replace(" ", "_")
    if not name:
        return JSONResponse({"error": "name required"}, status_code=400)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, generate_persona_questions, episode_id, name)
    return JSONResponse(result)


@api.get("/api/journey/personas")
async def journey_list_personas():
    """List built-in AI persona styles."""
    return JSONResponse({"personas": list(PERSONA_STYLES.keys())})


@api.get("/api/journey/episode/{episode_id}/script")
async def journey_episode_script(episode_id: int, persona: str = Query("default")):
    """Return Q+A script for an episode in dialogue format."""
    return JSONResponse(get_episode_script(episode_id, persona=persona))


@api.get("/api/journey/tts/status")
async def journey_tts_status():
    """Report whether the ElevenLabs voice engine is configured (API key present)."""
    has_key = bool(load_env_key("ELEVENLABS_API_KEY"))
    return JSONResponse({
        "available": has_key,
        "engine": "elevenlabs",
        "error": None if has_key else "ELEVENLABS_API_KEY not set in .env",
    })


@api.get("/api/journey/episode/{episode_id}/tts-stream")
async def journey_tts_stream(episode_id: int, persona: str = Query("default")):
    """
    SSE stream — voices the interviewer's lines via ElevenLabs, one clip at a time,
    so the browser plays them as they finish. Mark is the guest and speaks live, so
    his lines are not synthesized.

    Each event is JSON: {speaker, text, audio_b64, content_type} or {error} or {done}.
    """
    import base64 as _b64, json as _json
    import anyio
    from fastapi.responses import StreamingResponse

    script = get_episode_script(episode_id, persona=persona)
    if script.get("error"):
        async def _err():
            yield f"data: {_json.dumps({'error': script['error']})}\n\n"
        return StreamingResponse(_err(), media_type="text/event-stream")

    if not load_env_key("ELEVENLABS_API_KEY"):
        async def _nokey():
            yield f"data: {_json.dumps({'error': 'ELEVENLABS_API_KEY not set in .env'})}\n\n"
            yield f"data: {_json.dumps({'done': True})}\n\n"
        return StreamingResponse(_nokey(), media_type="text/event-stream")

    voice_id = persona_voice_id(persona)

    async def _generate():
        for idx, line in enumerate(script.get("lines", [])):
            text = line.get("text")
            speaker = line.get("speaker", "interviewer")
            # Only the interviewer is voiced — Mark (guest) speaks live.
            if speaker != "interviewer" or not text:
                continue
            try:
                audio = await anyio.to_thread.run_sync(elevenlabs_tts, text, voice_id)
                event = {
                    "idx": idx,
                    "speaker": speaker,
                    "text": text[:120],
                    "audio_b64": _b64.b64encode(audio).decode(),
                    "content_type": "audio/mpeg",
                }
            except Exception as e:
                event = {"idx": idx, "speaker": speaker, "text": text[:120], "error": str(e)}
            yield f"data: {_json.dumps(event)}\n\n"

        yield f"data: {_json.dumps({'done': True})}\n\n"

    return StreamingResponse(_generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@api.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not _cache["results"]:
        asyncio.create_task(_run_checks())
    return templates.TemplateResponse(request, "dashboard.html")
