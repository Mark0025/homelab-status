# Design: The Truth Layer — verify claims with browser-use, prove it to GitHub (#55)

> Tracking issue: [#55](https://github.com/Mark0025/homelab-status/issues/55). This doc is the durable, version-controlled design — committed alongside the code it describes. The point: **agents verify their own claims autonomously so Mark gets more work done** instead of checking things by hand.

## The problem: "success" is a proxy until something verifies it

Everything the app measures today — *deployed* (a route exists), *healthy* (a docker healthcheck), *grade B* (the code looks complete) — is a **proxy, not proof**. A claim like "repo X is deployed and does Y" is a **hypothesis** until something actually drives the live UI and checks. This layer makes claims **survive verification** = the real definition of "working".

---

## STEP 0 (do FIRST, verbose): learn from how MY repos already used browser-use / Playwright

Don't design blind — we have proven patterns (real data, 2026-06-27):

| Repo | How it used browser automation |
|---|---|
| **PeteRental_vapi_10_02_25** | Playwright + DuckDuckGo to SCRAPE rental listings (production automation) |
| **PAI** | Playwright as a primary dep (automation / E2E) |
| **Twilio_tools, localleasing, markcarpenter1-com** | `@playwright/test` for E2E UI testing |
| **browser-use** (cloned, Mark's 112 commits incl. ChatClaudeCode provider) | the api/worker/redis split + its task/result contract |

**Deliverable:** a short doc *"how we've used browser automation before"* — selectors, wait strategies, result shapes, failure modes — so the verifier **reuses proven patterns, not reinvented ones**.

---

## STEP 1: browser-use as a STANDALONE service the agent CALLS

Not embedded — a service. An agent (or homelab-status, or an agent-eos agent) calls it with a plain-English task + URL and gets back a **3-format report** = the proof currency:

```
POST browser-use  { task: "go to {url}, verify it does Y", url }
  -> worker drives a REAL browser (Playwright)
  -> REPORT:
       images        screenshots at key steps (visual proof)
       json          {steps[], found/not-found, http_status, console_errors}  (machine-readable)
       ui_language   "I saw the dashboard load; Services showed 88 up / 6 down; search worked"  (human)
```

---

## STEP 2: the verification pipeline (the conductor)

```
homelab-status (conductor — on nginx-network with browser-use + claude-http + GitHub)
  1. pick a testable CLAIM from the AI analysis ("repo X at {friendly_url} does Y")
  2. call browser-use -> images + json + ui_language
  3. claude-http reads the report: "claim said Y; browser saw Z. VERDICT: TRUE/FALSE + why"
  4. write PROOF to GitHub: issue/comment with screenshots (linked), the verdict, SSE live progress
  5. store an append-only verification snapshot (#53): claim + verified(t/f) + media_url + verdict
       -> a REFUTED claim = a real disagreement = an auto-issue (the daily-loop signal, #52)
```

---

## STEP 3: MEDIA LIFECYCLE — images/video must NOT build up

A real ops problem (echoes the LEGO log-rotation incident — unbounded artifacts fill disks). Enforce up front:

- **Retain only what's needed for proof**: key-step screenshots + verdict; **video only on failure / on demand**, not by default.
- **TTL + rotation**: media older than N days auto-deleted (cron); cap total size like docker `log-opts`.
- **Reference, don't embed**: GitHub issue **links** to a served media URL (homelab-status serves a bounded media dir); GitHub never stores the video.
- **Dedup**: a passing re-verify of an unchanged claim doesn't re-store identical media.
- **Decide where served**: a bounded `/media/verifications/` mount on homelab-status with a size cap + rotation, OR a blob store.

> Skip this and the verifier becomes a disk bomb. Design the lifecycle first.

---

## What EXISTS vs what we BUILD

| Piece | Status |
|---|---|
| browser-use service (api/worker/redis) | ✅ running, browser.markcarpenter1.com, plain-English tasks, Playwright |
| claude-http (verdict analyzer) | ✅ running, proven |
| append-only snapshots | ✅ built (#53) — verification snapshots slot in |
| past Playwright/browser-use patterns | ✅ exist in ~6 repos (Step 0) |
| **agent-eos (orchestrator)** | ⚠️ REAL but **D/prototype, empty README, no routes — UNPROVEN.** Don't design "how agent-eos calls this" against a shell. Keep the verifier **standalone/callable-by-anything**; verify agent-eos's real API before coupling. |
| browser-use API contract | ❌ **UNKNOWN** — couldn't reach it (SSH fail2ban + sandbox). MUST confirm before building dispatch. |
| the conductor (`verify.py`) | ❌ build |
| media lifecycle | ❌ build |
| write proof + SSE to GitHub | ❌ build |

## Phasing

- **Phase A (cheap truth, no browser)**: HTTP liveness — does `{friendly_url}` return 200 + expected content? + claude verdict + GitHub proof. Closes "deployed ≠ responding" now. *(No browser-use API needed — buildable immediately.)*
- **Phase B**: Step 0 study → browser-use standalone report → conductor → proof. Needs the browser-use contract + media lifecycle.
- **Phase C**: SSE live stream + auto-issue on refuted claims (the daily-loop close, #52).

## Hard rules

- A claim is a hypothesis until verified — UI/snapshots show **verified / unverified / refuted** distinctly, never "working" without proof.
- Refuted claims cite the screenshots + verdict as evidence (synthesis-discipline).
- browser-use runs against **our** live services only.
- **Media is bounded** — no unbounded image/video buildup.
- Don't couple to agent-eos until its API is real.

## Acceptance (mirrors #55)

- [ ] Step 0 doc exists (how we've used browser automation before)
- [ ] browser-use returns images + json + ui_language for a task
- [ ] a true claim verifies TRUE, a false claim verifies FALSE, both with evidence
- [ ] verification snapshot is append-only + linked to (bounded) media
- [ ] a refuted claim opens an AI-labeled issue citing the proof
- [ ] media lifecycle: old artifacts auto-rotate; total size capped

---

**Relates to:** daily loop (#52), AI analysis (#42), capability registry (#41/#45), append-only snapshots (#53), repo scout (#49). browser-use is currently only health-checked by the app — this is its first real *use*.
