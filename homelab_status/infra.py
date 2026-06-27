"""Consume the homelab diagram server's LIVE map (#14: consume, don't recompute).

The diagram server (homelab-diagram-server, :8100 in-container / :8101 host) already
knows the RUNTIME truth — which containers exist, their health, public URLs, SSL,
deployment status — and renders Mermaid. homelab-status was blind to all of that
(it only knew git/learning). This module reads that map so a repo's learning view
can answer 'is it actually deployed and running?' WITHOUT rebuilding the registry
(replaces the hardcoded services.py drift source).

Both services are on `nginx-network`, so the in-container call by name works.
Per principle 1, a failed fetch from a sandbox is NOT 'the service is down' — we
fall back to an empty map and say so, never fabricate.
"""

import os

import httpx
from loguru import logger

# In-container: reach the diagram server by name on the shared docker network.
# Overridable for host/testing via env.
DIAGRAM_BASE = os.environ.get("DIAGRAM_BASE_URL", "http://homelab-diagram-server:8100")
# The /api/unified/* endpoints compute live across 120+ containers and are SLOW
# (verified: >10s from inside the network). Use a generous timeout AND cache, so
# we never block a request on the diagram server's recompute.
_TIMEOUT = 30.0
_CACHE_TTL = 120  # seconds
_cache: dict[str, tuple[float, object]] = {}


async def _get(path: str, ttl: int = _CACHE_TTL) -> dict | list | None:
    import time
    now = time.monotonic()
    hit = _cache.get(path)
    if hit and (now - hit[0]) < ttl:
        return hit[1]  # type: ignore[return-value]
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get(f"{DIAGRAM_BASE}{path}")
            if r.status_code == 200:
                data = r.json()
                _cache[path] = (now, data)
                return data
            logger.warning(f"diagram server {path} -> {r.status_code}")
    except Exception as e:
        # NOT 'service down' — just slow/unreachable from here. Caller falls back;
        # serve stale cache if we have any rather than nothing.
        logger.warning(f"diagram server slow/unreachable at {DIAGRAM_BASE}{path}: {e}")
        if hit:
            return hit[1]  # type: ignore[return-value]
    return None


async def runtime_summary() -> dict:
    """The whole-homelab overview the diagram server already computes."""
    data = await _get("/api/unified/summary")
    if not data:
        return {"available": False, "reason": "diagram server unreachable from here"}
    data["available"] = True
    return data


async def container_runtime() -> dict[str, dict]:
    """Map container_name -> {status, health, url, public_url, ssl, image}.

    The RUNTIME truth homelab-status was missing: is it deployed & running & live?
    """
    data = await _get("/api/unified/projects")
    out: dict[str, dict] = {}
    if not isinstance(data, dict):
        return out
    for proj in (data.get("projects") or {}).values():
        for c in proj.get("containers", []) or []:
            name = c.get("name")
            if not name:
                continue
            out[name] = {
                "status": c.get("status", ""),
                "health": c.get("health", ""),
                "url": c.get("url", ""),
                "public_url": c.get("public_url", ""),
                "ssl_enabled": c.get("ssl_enabled", False),
                "is_public": c.get("is_public", False),
                "image": c.get("image", ""),
                "project": c.get("project", ""),
            }
    return out


async def npm_proxies() -> list[dict]:
    """The NGINX-Proxy-Manager friendly-URL map (diagram /api/unified/npm).

    Each: {domains:[friendly_url], forward_host, forward_port, ssl, container,
    project_slug, github_repo, access_list}. This is the FRIENDLY-name layer —
    portainer.markcarpenter1.com -> portainer:9443 -> Clerk/ACL auth. The app
    already has access; we just consume it.
    """
    data = await _get("/api/unified/npm")
    if isinstance(data, dict):
        return data.get("domains", []) or []
    return []


def friendly_urls_for(proxies: list[dict], repo: str, containers: list[str]) -> list[dict]:
    """All friendly URLs that front this repo's containers. Matches an NPM proxy
    when its forward_host/container/github_repo ties to the repo or one of its
    running containers. Returns [{url, forward, ssl, auth}]."""
    rn = _norm(repo)
    cset = {_norm(c) for c in containers}
    out: list[dict] = []
    for p in proxies:
        host = _norm(p.get("forward_host", ""))
        cont = _norm(p.get("container", ""))
        gh = _norm(p.get("github_repo", ""))
        if (host in cset or cont in cset or rn in host or rn in cont
                or (gh and rn in gh)):
            for dom in (p.get("domains") or []):
                out.append({
                    "url": ("https://" if p.get("ssl") else "http://") + dom,
                    "forward": f"{p.get('forward_host')}:{p.get('forward_port')}",
                    "ssl": bool(p.get("ssl")),
                    "auth": p.get("access_list") or ("protected" if p.get("access_list_id") else "public"),
                })
    return out


def _norm(s: str) -> str:
    """Normalize a name for matching: lower-case, and _/spaces -> -."""
    return (s or "").lower().replace("_", "-").replace(" ", "-")


def runtime_for_repo(container_map: dict[str, dict], repo: str) -> dict | None:
    """Match a repo to its running container(s). A repo deploys as 1..N containers
    whose NAMES often differ from the repo (Twilio_tools -> twilio-backend,
    twilio-frontend, twilio-tools-webhook, ...). The reliable link is the
    compose-project name, embedded in the IMAGE (twilio-tools-twilio-backend).
    So match the normalized repo against each container's NAME and IMAGE.

    Returns the primary match enriched with ALL matching containers (a repo can
    run many), or honest None when nothing matches — never a guess.
    """
    rn = _norm(repo)
    matches: list[dict] = []
    for name, rt in container_map.items():
        nn = _norm(name)
        if rn in nn or nn in rn or rn in _norm(rt.get("image", "")):
            matches.append({"container": name, **rt})
    if not matches:
        return None
    primary = next((m for m in matches if _norm(m["container"]) == rn), None)
    if not primary:
        primary = next((m for m in matches if m.get("health") == "healthy"), matches[0])
    return {**primary,
            "containers": [m["container"] for m in matches],
            "container_count": len(matches)}
