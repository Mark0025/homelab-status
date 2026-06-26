# What homelab-status can do better now

> A plain-English record of how the app's capabilities changed across the 2026-06 hardening work (issues #18–#25, PRs #17, #21, #24, #26, #27, #28, #29). For *what each tab shows*, see `WHAT-HOMELAB-STATUS-DOES.md`; for *how to deploy*, see `DEPLOY-RUNBOOK.md`. Every claim here was verified live on the Hetzner container, not assumed.

---

## The one-line summary

homelab-status went from **honor-system, frozen-in-Python, confidently-wrong, silently-broken, and undeployable** → to **a gated, tested, observable, self-deploying app whose UI tells you when its own data is stale.** The data and features didn't change; the *trustworthiness and shippability* did.

---

## 1. It now ships itself — "merge = live"

**Before:** A fix could merge to `main` and the build a fresh image, but nothing put it on Hetzner. Someone had to remember to SSH in and `docker compose pull`. In practice, **5 merged fixes sat undeployed** while the live dashboard stayed broken.

**Now:** A name-scoped Watchtower (the maintained `nicholas-fedor` fork) watches **only** the `homelab-status` container and auto-pulls a new image within ~5 minutes of a merge. The other ~106 containers on the host are untouched.

**Functionally:** merge a PR → it's live, automatically, with no manual step. The thing you look at stays current with the code.

*(Getting here surfaced and fixed real infra bugs: the container ran from a loose copy dir with no token; the abandoned `containrrr/watchtower` was too old for the host's Docker API; and the standard watchtower label was already on 6 other containers so label-scoping was unsafe. All corrected — see PRs #28/#29.)*

---

## 2. It no longer lies silently — failures are loud

**Before:** With no GitHub token, every API fetch sent `Authorization: Bearer ` (empty), GitHub rejected it, the error was swallowed as a debug warning, and the app **silently ingested 0 commits** — leaving profiles stuck at stale numbers (homelab-status showed 1 commit; reality was 28).

**Now:** A missing token **raises loudly** — `refresh_all` aborts with a clear error instead of fetching nothing. The bug class that hid the stale data can't recur silently.

**Functionally:** if ingestion can't authenticate, you'll know immediately, not weeks later via wrong numbers.

---

## 3. The UI tells you when its own data is suspect

**Before:** The dashboard rendered stale, broken, and correct numbers identically. `commits_last_7d: 0` looked like "quiet week" but actually meant "sync broken." For a *source-of-truth* tool, that's the worst failure mode — confidently wrong with no tell.

**Now:** A top-of-page freshness banner distinguishes three states: **BROKEN** (never synced / 0 commits ingested — likely a token problem), **WARN** (0 commits in 7 days, or cache past TTL), and **hidden** (data is fresh). It updates on every load, on any tab.

**Functionally:** you can tell "nothing happened" from "the sync is broken" at a glance.

---

## 4. The server is observable and disk-safe

**Before:** loguru was configured only on the CLI path, so the *running container* logged via loguru's unconfigured default sink — unstructured, no level control. And docker logging had **no rotation** (the exact `voice-app`-filled-114GB-disk risk from the LEGO rules).

**Now:** logging is configured for both entrypoints via one shared, `LOG_LEVEL`-driven sink (structured `time | level | name:function:line | message`), and the container caps logs at `50m × 3`.

**Functionally:** you can read what the server is doing, and one chatty container can't fill the host disk.

---

## 5. The UI is no longer welded into Python — it's testable

**Before:** `web.py` was 2,347 lines; ~1,800 of them were the entire frontend (HTML + 1,250 lines of JS + CSS) trapped inside one Python string literal. Unlintable, untestable, un-accessible.

**Now:** the frontend lives in real files — `templates/dashboard.html`, `static/dashboard.css`, `static/dashboard.js` — served by the same FastAPI container via Jinja2 + StaticFiles. `web.py` dropped to ~528 lines. The extraction was proven **byte-for-byte identical** (the browser receives the same page).

**Functionally:** the UI can now be linted, tested, and made accessible — and the freshness banner (#3) was clean to build because of it.

---

## 6. Change is now safe by construction (pipeline + tests)

**Before:** `main` had **no branch protection**, all three merge strategies were allowed (which caused duplicate merge-commits), and there were **0 tests** — CI only ran *after* merge, so a broken change reached production unchecked.

**Now:**
- `main` is protected: PR required, **`build` is a required status check**, no force-push, no deletion, merge-commits disabled (squash-only).
- The CI `build` gate runs on every PR (was deploy-only) and now runs **13 unit tests** plus the Docker build.
- A repo-rules generator was fixed to report *live* branch-protection state instead of a stale guess.

**Functionally:** you can't merge an untested or unbuildable change, and `main` reads as a clean, bisectable changelog.

---

## The shape of the improvement

Every fix this cycle addressed the same root pattern — **truth that was frozen, hidden, or unshippable:**

| Problem shape | Fix |
|---|---|
| UI frozen in Python strings | extracted to templates/static (#25) |
| Failure hidden (silent 0-fetch) | fail loud on missing token (#20) |
| Stale data shown as fresh | freshness banner (#23) |
| Server blind + disk-risky | loguru in container + log rotation (#22) |
| Code merged but never shipped | name-scoped Watchtower auto-deploy (#19) |
| Change unguarded | branch protection + CI gate + tests (#16/#18) |

---

## What's still NOT done (so nobody assumes it is)

- **Live infrastructure data (#14)** — the Services tab still reads the hardcoded `services.py` registry, not the live diagram-server/NPM APIs. This is the last big "frozen-in-Python" data source and the next real feature.
- **Learning verdict / scoring (#13)** — the app still *describes* (commits, fix ratios) rather than *concludes* ("this fix held vs was re-fixed"). The git-advisor concept (`GIT-ADVISOR.md`, not yet built) is #13 Layer A.
- **Accessibility** — the UI is now extractable/testable, but no a11y pass has been done yet.
