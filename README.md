# homelab-status

> **📌 This README is DOCS & UNDERSTANDING captured 2026-06-17 — the shared map before the build.**
> The "becoming" sections describe epics [#13](https://github.com/Mark0025/homelab-status/issues/13) and [#14](https://github.com/Mark0025/homelab-status/issues/14), which are **not implemented yet**. The next working session ties them in. Read this to understand what the app *is* and *where it's going*, not as a description of shipped features beyond "What it does today."

**homelab-status turns everything built across 200+ repos and 4 servers into one learnable model** — so we stop repeating mistakes, stop starting fresh, and learn from the architecture (and the issues/PRs that solved its problems) every day.

It runs as a container on the Hetzner homelab (`:8800`, on `nginx-network`) and is the source-of-truth app for Mark's internal learning program.

---

## What it does TODAY (shipped)

| Capability | How |
|---|---|
| **Cross-repo GitHub ingestion** | Pulls 3 orgs into SQLite (`status.db`): **121 repos, 5,296 commits, 938 PRs, 121 `project_profiles`** (detected stack, agent attribution, fix-commit ratio, has_docker/tests/ci). |
| **Plan/design doc index** | Reads the local `mdops-mac.db` (**4,603 docs**) to tie repos to their planning docs. |
| **Journey / interview layer** | Turns real commit history into voice-interview questions (ElevenLabs TTS + OpenRouter personas). |
| **Service health dashboard** | Health-checks ~60 homelab services via a hand-maintained `services.py` registry + a FastAPI/Plotly web UI. |

**Stack:** Python 3.11 · FastAPI + uvicorn · Typer (CLI) · httpx · pydantic · pandas + plotly · anthropic · SQLite. Managed with `uv`. Deployed via `docker.yml` → GHCR image → Hetzner.

```bash
uv run homelab-status --help     # CLI
# the web dashboard serves on :8800 in the container
```

---

## What it's BECOMING (the two epics — DOCS, not built yet)

These are the design epics that this docs pass establishes. They are the **map**; the build comes next session.

### [#13](https://github.com/Mark0025/homelab-status/issues/13) — the repo-learning-scoring engine
For each repo, conclude and score (all from real data already in `status.db` + `gh`):
- **Layer A — Learning Verdict:** *what we got right vs where we misunderstood* — detected from re-fix chains in real PR history (e.g. a `fix:` PR re-touching the same file a prior `fix:` touched = the first fix didn't hold).
- **Layer B — Best-Practices Score + Dependency Use:** score each repo against *current official* best-practices for its detected stack (Next.js/shadcn/TypeScript via the `vercel:*` skills; Python via the `Ref` MCP), map each dependency's functional use, and guard against bad info (a video claim accepted only if it agrees with official docs).
- **Layer D — Governance & Deploy-Strategy Score:** branch-protection / merge-gates / deploy strategy vs Mark's own `DEV_WORKFLOW_DISCIPLINE` rules (Tier 1) + industry standards (Tier 2), with a ledger of real deploy-failure incidents.

### [#14](https://github.com/Mark0025/homelab-status/issues/14) — the Architecture Intelligence frame
Join the APIs that **already exist** across the 4 servers into ONE living model — so we resolve drift, model new products from working infra (instead of starting fresh), and see how systems connect / align / disconnect / need restructure.

---

## The architecture this app models (4 servers, one Tailscale mesh)

| Server | Tailnet IP | Role | Source of truth for |
|---|---|---|---|
| **M5** (this Mac) | `100.102.154.102` | Primary dev / design | code intent |
| **M1** | `100.119.236.63` | Secondary (often offline) | — |
| **Hetzner** `myhomelab` | `100.100.92.100` | Homelab execution — ~104 containers, NPM, Terry fleet | running infrastructure state |
| **Hostinger** `srv1551269` | `100.83.246.107` | Hermes/Adam agent harness (OpenClaw) | agent orchestration |

**Runtime security model (important):** services reach the internet **only** through the **NGINX Proxy Manager** reverse proxy (SSL, `*.markcarpenter1.com`) — no firewall holes punched; everything else sits on internal Docker networks (`nginx-network` / `pete-network`). *GitHub branch protection is a separate concern (Git merge-gates), not runtime exposure — never conflate the two.*

---

## Three operating principles (learned the hard way)

Captured in `~/PAI/.claude/context/learnings/2026-06-17-sandbox-reachability-is-not-service-health-consume-dont-recompute.md`:

1. **Sandbox reachability ≠ service health** — a `curl`/`000` from an AI/automation environment is about *its* egress, not the service. Verify on the host before saying "down."
2. **Name the layer** — Git merge-gates ≠ runtime exposure (NPM handles the latter, deliberately).
3. **Consume, don't recompute** — almost everything already has an API (NPM `:81`, the diagram server, GitHub, mdops). Join them; don't re-derive or hardcode a registry that drifts.

---

## Status

🚧 **Active design phase.** The engine in #13/#14 is documented, not yet implemented. The first build is the proven cheap wire-in: **consume the live diagram server + NPM API instead of the hardcoded `services.py`.** See the epics for the full build order.
