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

## Git workflow + CI/CD — the conveyor belt (enforced by config, not honor system)

> A change travels six stations from your edit to a running container on Hetzner. Each station is a LEGO step (manual → brick → house). **Verify live state with `gh api`, don't trust this prose** (principle 1) — but this is what was configured as of 2026-06-18.

```
EDIT ─► [1] branch ─► [2] PR build gate ─► [3] main protection ─► [4] build+push ─► [5] MANUAL deploy ─► [6] running
        (photocopy)   (CI: pull_request)   (squash-only, no       (CI: push:main,   (ssh homelab,        (uvicorn :8800,
                       builds, no push)     direct push, no force) ships :latest)    docker compose pull) nginx-network)
```

1. **Branch** `type/N-description` off `main`. Never edit `main` directly.
2. **PR build gate** — `.github/workflows/docker.yml` job `build` runs on `pull_request`: it `docker build`s the image with `push: false` to **prove it still builds**, then discards it. Red here = blocked merge (`build` is a required status check). This is "test that what we did doesn't break" — see the gap note below.
3. **`main` is protected** (live config, verify with `gh api repos/Mark0025/homelab-status/branches/main/protection`): PR required (0 reviewers, solo), required check `build`, **no force-push, no deletion**, and **merge-commits are DISABLED at the repo** so the only merge button is **Squash** (rebase kept as a rare escape hatch). `enforce_admins:false` = **Mark may override for a true hotfix; an AI agent must NEVER** (same boundary as Terry → `autonomous-work` only, and Adam → can't push at all).
4. **Build + push** — job `build-and-push` runs only on `push: main` (after merge) and ships `ghcr.io/mark0025/homelab-status:latest` (+ `sha-` tag) to GHCR. Inspection (step 2) and deploy (step 4) are deliberately separate jobs.
5. **⚠️ Deploy to Hetzner is MANUAL.** Nothing auto-pulls the image — there is no Watchtower/webhook in this repo (tracked: #19). `docker-compose.yml` pins `:latest`, so the running container stays on the OLD image until someone runs `ssh homelab` → `docker compose pull homelab-status && docker compose up -d`. "Push to Hetzner" really means "push to GHCR, then deploy." (LEGO rule: server PULLs + RUNs, never builds.)
6. **Running** — container `homelab-status` on `nginx-network` (NPM is the HTTPS doorman = *runtime* layer, NOT the Git gate — principle 2). `/data` volume persists `status.db`; it **read-only-mounts** `mdops-mac.db` from `/home/mark/00Myhomelab/...` (it CONSUMES another system's data; see "connected apps" below).

### Commit / PR conventions
- **One issue per PR.** `commit: prefix: description (#N)`. The squash-commit **body** = one bullet per logical change (the `.github/pull_request_template.md` + `.gitmessage` prefill this) — that body is `main`'s durable history; the PR page keeps every original commit forever.
- End commit messages with the `Co-Authored-By: Claude Opus 4.8 (1M context)` trailer.
- Run `/simplify` before committing; `/code-review` for bug-hunting.

### Known gaps (do NOT assume these are handled)
- **No unit tests** (#18). The `build` gate proves the image *compiles*, not that it *works*. Global rule "no endpoint without a test" is currently violated here — adding `uv run pytest` to the gate is the next hardening.
- **No auto-deploy** to Hetzner (#19) — step 5 is manual.

### Connected apps (blast radius)
- **Reads** `mdops-mac.db` (written by the MDDPY/Terry system) via read-only mount.
- **Will read** the diagram server `/api/unified/*` + NPM `:81` once EPIC #14 replaces `services.py` (unbuilt).
- **Pulls** the GitHub API (3 orgs) → writes only its own `status.db`. Writes to no other app — low blast radius, which is why it's a safe repo to perfect this CI/CD discipline first.
- **Docs vs build:** epics #13/#14 are **design docs, not implemented.** First build = #14's diagram/NPM wire-in to replace `services.py`. Don't claim a layer is built until it is.

## When uncertain

- Verify infra claims on the host before asserting them (principle 1).
- Prefer reading an existing API/DB over a multi-agent workflow (principle 3) — reserve workflows for genuine cross-repo synthesis.
- Ask Mark when a design choice affects the epics' intent.
