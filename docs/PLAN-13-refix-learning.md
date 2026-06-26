# Plan #13 — the Learning Verdict: re-fix detection → Mermaid story → plan-doc join

> Implements EPIC #13 Layer A. **Goal:** stop the app at "lists every fix" and make it *conclude* — "this fix didn't hold," shown as a visual story that connects the re-fix back to what the plan/.md said and why it failed. Multi-PR. Build the engine first, validate on real data, THEN visualize (never draw diagrams of unvalidated conclusions).

---

## The gap (how the app looks at fixes today)

The app already has a complete fix lens — verified in code:
```
gh_commits (commit_type='fix') → project_intel.extract_fix_patterns()
  {repo, what_broke, how_fixed, agent, model, pr_number, days_to_fix, commit_sha}
  → /api/intel/fixes → dashboard.js renderFixes() → the "Fixes" view
```
But it shows fixes as a **flat, unconnected list**. It never asks: *did this fix relate to an earlier fix?* The learning is the correlation, and it's missing.

## Validated signal (on REAL data, 2026-06-26)

Prototyped fix-subject similarity on Mark's real repos (forks excluded). Threshold: **Jaccard ≥ 0.5 on significant words (>3 chars, `fix:` prefix stripped)**.

| repo | fixes | re-fix pairs | example found |
|---|---|---|---|
| pete-db | 90 | 3 | "Use API_URL env var" ↔ "Add API_URL env var" (0.60); docker host-paths ↔ container-paths (0.56) |
| app.Aireinvestor | 186 | 20 | Stripe checkout fixed repeatedly |
| wes | 189 | 12 | role utilities split (1.00 = redone) |
| Twilio_tools | 71 | **0** | correctly quiet — no false positives |
| peterei_intercom | 69 | **0** | correctly quiet |

The signal is real, finds genuine "didn't hold" cases, and stays quiet where there's nothing. `files_changed` is only a COUNT (no paths stored), and `Closes #N` covers only ~13% of fixes — so **text-similarity is the right v1 signal**; file-path correlation would need new ingestion (future).

## The three stages (each its own PR, each reuses existing app code)

### PR 1 — the engine: `detect_refixes()`  ← BUILD FIRST
- New function in `project_intel.py` next to `extract_fix_patterns()` (same module/pattern).
- For each REAL repo (exclude forks via a fork list / SKIP_REPOS), find fix pairs with Jaccard ≥ 0.5 within a time window (the earlier fix is the one that "didn't hold").
- Returns structured re-fixes: `{repo, fix_a:{sha,subject,date}, fix_b:{...}, similarity, days_between}`.
- Route `GET /api/intel/refixes`; surface as a "⚠️ re-fixed" marker + a Learnings count in the existing Intel view. Tested. List form only — NO graph yet.
- **Acceptance:** finds the validated pete-db/app.Aireinvestor pairs; stays empty for Twilio_tools.

### PR 2 — the Mermaid story
- A route emits **Mermaid** syntax for a repo's re-fix chains: `plan → fix#1 → (didn't hold) → fix#2 → verdict`.
- Dashboard renders it (Mermaid client include; the homelab also has a diagram server). New "Learnings" view.
- Mermaid MCP (`mcp__claude_ai_Mermaid_Chart__validate_and_render`) can validate the generated syntax in tests.

### PR 3 — the plan-doc join ("why it failed")
- Attach the plan: reuse `mdops.docs_for_repo()` + `enricher`'s vision-vs-reality logic (already links repo → plan .md and compares plan-said vs shipped).
- The graph node becomes: *plan said X → fixed twice → the plan underspecified the thing that broke.* This is the actual learning verdict.

## Why this order

Building the graph (PR 2) before the validated engine (PR 1) would mean drawing pretty diagrams of possibly-wrong correlations — the exact "confidently wrong" trap the 2026-06 hardening eliminated. Engine → prove on real data → visualize → explain.

## Reuse map (don't reinvent)

| Need | Existing app code |
|---|---|
| extract fixes | `project_intel.extract_fix_patterns()` |
| exclude forks | `git_history.SKIP_REPOS` |
| repo → plan .md | `mdops.docs_for_repo()` (git_remotes match, PR #6) |
| plan vs reality | `enricher.py` (vision/reality scan) |
| render | Mermaid (client include) + diagram server + Mermaid MCP for validation |

## Out of scope (named, not silently dropped)

- File-path-level re-fix correlation (needs ingesting commit file lists — not stored today).
- Best-practice scoring (#13 Layer B) — separate, needs reference docs.
- Cross-repo dedup ("solved this in repo X") — a natural PR 4 once same-repo works.
