"""Async HTTP checker — probes endpoints, detects docs, parses metadata, fetches OpenAPI routes."""

import asyncio
import re
import time
from typing import Any

import httpx
from loguru import logger
from pydantic import BaseModel, Field

from .services import Service

AUTH_REDIRECT_SIGNALS = frozenset({"/sign-in", "/login", "/auth", "/signin", "/authenticate"})
TIMEOUT = httpx.Timeout(10.0, connect=5.0)


class ApiRoute(BaseModel):
    method: str
    path: str
    summary: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    parameters: list[dict[str, Any]] = Field(default_factory=list)
    request_body: dict[str, Any] | None = None
    responses: dict[str, str] = Field(default_factory=dict)
    deprecated: bool = False


class CheckResult(BaseModel):
    service: Service
    status_code: int | None = None
    response_time_ms: float = 0
    reachable: bool = False
    redirected_to: str = ""
    redirect_is_auth: bool = False
    has_docs: bool = False
    docs_url: str = ""
    has_health: bool = False
    health_status: str = ""
    server_header: str = ""
    content_type: str = ""
    title: str = ""
    error: str = ""
    api_routes: list[ApiRoute] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}


def _is_auth_redirect(location: str) -> bool:
    lower = location.lower()
    return any(sig in lower for sig in AUTH_REDIRECT_SIGNALS)


def _extract_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip()[:120] if match else ""


def _parse_openapi(schema: dict[str, Any]) -> list[ApiRoute]:
    routes: list[ApiRoute] = []
    for path, path_item in schema.get("paths", {}).items():
        for method in ("get", "post", "put", "patch", "delete", "head", "options"):
            op = path_item.get(method)
            if not op:
                continue
            routes.append(ApiRoute(
                method=method.upper(),
                path=path,
                summary=op.get("summary", ""),
                description=op.get("description", ""),
                tags=op.get("tags", []),
                parameters=op.get("parameters", []),
                request_body=op.get("requestBody"),
                responses={
                    code: resp.get("description", "")
                    for code, resp in op.get("responses", {}).items()
                },
                deprecated=op.get("deprecated", False),
            ))
    return routes


async def _fetch_openapi(client: httpx.AsyncClient, base_url: str) -> list[ApiRoute]:
    for path in ("/openapi.json", "/api/openapi.json"):
        url = base_url.rstrip("/") + path
        try:
            resp = await client.get(url, follow_redirects=False, timeout=TIMEOUT)
            if resp.status_code == 200 and "json" in resp.headers.get("content-type", ""):
                routes = _parse_openapi(resp.json())
                if routes:
                    logger.debug(f"OpenAPI: {base_url} → {len(routes)} routes")
                    return routes
        except Exception:
            pass
    return []


async def check_service(client: httpx.AsyncClient, service: Service) -> CheckResult:
    result = CheckResult(service=service)
    start = time.perf_counter()

    try:
        resp = await client.get(service.url, follow_redirects=True, timeout=TIMEOUT)
        result.response_time_ms = (time.perf_counter() - start) * 1000
        result.status_code = resp.status_code
        result.reachable = resp.status_code < 500
        result.server_header = resp.headers.get("server", "")
        result.content_type = resp.headers.get("content-type", "")

        final_url = str(resp.url)
        if final_url != service.url:
            result.redirected_to = final_url
            result.redirect_is_auth = _is_auth_redirect(final_url)

        if resp.headers.get("x-clerk-auth-status") == "signed-out":
            result.redirect_is_auth = True

        if "text/html" in result.content_type:
            result.title = _extract_title(resp.text)

    except httpx.TimeoutException:
        result.error = "timeout"
        result.response_time_ms = (time.perf_counter() - start) * 1000
        logger.warning(f"[{service.name}] timeout after {result.response_time_ms:.0f}ms")
        return result
    except httpx.ConnectError as e:
        result.error = f"connect_error: {e}"
        result.response_time_ms = (time.perf_counter() - start) * 1000
        logger.warning(f"[{service.name}] connect error: {e}")
        return result
    except Exception as e:
        result.error = str(e)
        result.response_time_ms = (time.perf_counter() - start) * 1000
        logger.error(f"[{service.name}] unexpected error: {e}")
        return result

    # ── Docs probe ─────────────────────────────────────────────────────────
    if service.has_docs_path:
        docs_url = service.url.rstrip("/") + service.has_docs_path
        try:
            docs_resp = await client.get(docs_url, follow_redirects=True, timeout=TIMEOUT)
            if docs_resp.status_code == 200:
                result.has_docs = True
                result.docs_url = docs_url
        except Exception:
            pass

    # ── Health probe ───────────────────────────────────────────────────────
    if service.health_path:
        health_url = service.url.rstrip("/") + service.health_path
        try:
            h_resp = await client.get(health_url, follow_redirects=True, timeout=TIMEOUT)
            if h_resp.status_code == 200:
                result.has_health = True
                try:
                    result.health_status = h_resp.json().get("status", "ok")
                except Exception:
                    result.health_status = "ok"
        except Exception:
            pass

    # ── OpenAPI introspection ──────────────────────────────────────────────
    if result.reachable and not result.redirect_is_auth:
        result.api_routes = await _fetch_openapi(client, service.url)

    return result


async def check_all(services: list[Service], concurrency: int = 20) -> list[CheckResult]:
    sem = asyncio.Semaphore(concurrency)
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=10)

    async def _bounded(client: httpx.AsyncClient, svc: Service) -> CheckResult:
        async with sem:
            logger.info(f"Checking: {svc.name}")
            return await check_service(client, svc)

    async with httpx.AsyncClient(limits=limits, verify=True) as client:
        return list(await asyncio.gather(*[_bounded(client, svc) for svc in services]))
