# CLAUDE.md — how to work in homelab-status

> Project instructions for Claude working in this repo. The full *vision and design* live in epics [#13](https://github.com/Mark0025/homelab-status/issues/13) and [#14](https://github.com/Mark0025/homelab-status/issues/14) and the `README.md` — **read those for WHAT we're building; this file is HOW to work here.** If this file and an epic ever disagree, the epic wins for design intent; tell Mark and reconcile.

## What this app is (one line)

homelab-status turns 200+ repos and 4 servers into one learnable model — it ingests cross-repo GitHub data, derives per-repo profiles, and (per #13/#14, not yet built) will score learning/best-practices/governance and consume the live infra APIs. It runs as a container on Hetzner (`:8800`, `nginx-network`).

## Three operating principles (apply to every task here)

These came from real session mistakes — see `~/PAI/.claude/context/learnings/2026-06-17-sandbox-reachability-is-not-service-health-consume-dont-recompute.md`.

1. **Sandbox reachability ≠ service health.** A `curl`/`000`/timeout from *this* execution environment is evidence about its egress, NOT the service. The Claude sandbox is egress-restricted; public `*.markcarpenter1.com` URLs time out here even when they work in Mark's browser. **Never report a service as "down" from a failed probe — verify on the host** (`ssh homelab` → `docker ps`, healthcheck) or ask Mark.
2. **Name the layer (don't conflate Git with runtime).** GitHub branch protection = Git *merge-gates* (who can merge `main`). Runtime security = the NGINX Proxy Manager reverse proxy (no firewall holes; internal Docker networks). A repo with no branch protection is NOT an exposed service. Keep these strictly separate in any analysis.
3. **Consume, don't recompute.** Almost everything already exposes an API or DB. Query the system that owns the truth; don't re-derive with a big workflow or hardcode a copy that drifts. The existing `services.py` registry is exactly that drift problem — treat it as fallback, not truth.

## The data flow (how this code is structured)

```
GitHub API ─┐
mdops-mac.db ┼─→ ingest/derive ─→ status.db (SQLite) ─→ web.py (FastAPI + Plotly UI) + main.py (Typer CLI)
local clones ┘                         ▲
                                       └─ project_profiles, gh_commits/PRs, journey_*, etc.
```

| File | Role | Notes |
|---|---|---|
| `db.py` | SQLite schema + `_conn()` + migrations | **Reuse `_conn()` / the upsert pattern for any new table.** Don't add a second persistence mechanism. |
| `git_history.py` | GitHub ingestion (3 orgs, cache TTLs) | Auth via `GITHUB_PERSONAL_ACCESS_TOKEN`/`GH_TOKEN`/`gh auth token`. |
| `project_intel.py` | Per-repo `project_profiles` (stack detection, agent attribution, fix ratio) | `ProjectProfile` is a **pydantic `BaseModel`**. Stack = substring keyword match. Largest/most central module. |
| `enricher.py` | Turns commit history + mdops/plan docs into specific interview questions | Reads the local `mdops-mac.db`. |
| `mdops.py` | Direct SQLite reads of `mdops-mac.db` (4,603 docs) | Path via `MDOPS_DB_PATH`. |
| `journey.py` | Journey/interview layer (ElevenLabs TTS, OpenRouter personas, deps snapshot) | |
| `timeline.py` | Commit classification (feat/fix/…), merge-strategy, bot detection | Source of `merge_strategy`, `commit_type` used by future scoring. |
| `services.py` | **Hardcoded** ~60-service registry | ⚠️ Drift source. #14's first build replaces this with the live diagram server + NPM API. Don't expand it by hand if you can read live instead. |
| `web.py` | FastAPI routes + single-page dashboard | Largest file; intel/journey/status/mdops/timeline route groups. |
| `main.py` | Typer CLI entrypoint (`homelab-status`) | |
| `checker.py`, `report.py` | endpoint health checks + reporting | |

## Conventions (match the codebase)

- **Python 3.11, managed with `uv`.** Run via `uv run homelab-status …`. Never `pip`.
- **SQLite via `db.py:_conn()`** for all persistence. New tables follow the existing `CREATE TABLE IF NOT EXISTS` + upsert style.
- **pydantic models** at boundaries (already used, e.g. `ProjectProfile`).
- **httpx (async)** for HTTP; **loguru** for logs; **plotly + pandas** for charts; **typer + rich** for CLI.
- Keep new code in the same flat `homelab_status/` module style; don't introduce a framework or restructure without asking.

## Getting REAL infrastructure data (cheaply, per principle 3)

When you need live infra truth, in order of preference:
1. **Public HTTPS the way Mark uses it** (he has Clerk auth on his machine): `diagram.markcarpenter1.com`, the service URLs. Note: **this works for Mark, may NOT work from the Claude sandbox** — don't conclude failure from a sandbox timeout.
2. **Hetzner over Tailscale:** `ssh homelab` (alias → `178.156.203.55`; tailnet `myhomelab` = `100.100.92.100`). Then `docker ps`, `docker inspect`, `docker network ls`.
3. **NPM REST API** on `:81` (live, returns proxy-host data) and the diagram server's `/api/unified/*` (FastAPI, container `:8100`, host `:8101`) — the runtime/NPM source of truth. Both `homelab-status` and `homelab-diagram-server` are on `nginx-network`, so in-container calls by name work too.
4. **The app's own `status.db`** for already-ingested GitHub/profile data — don't re-fetch what's stored.

See memory `homelab-status-knowledge-sources` for the full source map.

## Workflow discipline (from Mark's global rules)

- **Branch** `type/N-description` from main; **commit** `prefix: description (#N)`; **squash-merge** PR with tests checkbox + issue ref.
- **One issue per PR.** End commit messages with the `Co-Authored-By: Claude Opus 4.8 (1M context)` trailer.
- Run `/simplify` before committing; `/code-review` for bug-hunting.
- **Docs vs build:** epics #13/#14 are currently **design docs, not implemented.** When you start building, the first piece is #14's diagram-server/NPM wire-in to replace `services.py`. Don't claim a layer is built until it is.

## When uncertain

- Verify infra claims on the host before asserting them (principle 1).
- Prefer reading an existing API/DB over a multi-agent workflow (principle 3) — reserve workflows for genuine cross-repo synthesis.
- Ask Mark when a design choice affects the epics' intent.
