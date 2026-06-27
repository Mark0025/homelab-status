# LLM repo-analysis runbook (#42)

> Synthesizes a real purpose + 'why' for every repo (esp. the ~35% with thin/empty
> READMEs) by reading the REAL code and asking an LLM. Backend = Mark's own
> **claude-http** gateway (go-local-aibot), model `claude-fast:haiku` (lean Claude).

## How it works

```
host cron (every N min)  →  POST /api/registry/analyze?limit=10
   → analyze_all(): pick repos with no analysis yet (resumable)
   → per repo: code_audit reads real deps/routes/README
             → POST http://claude-http:8765/v1/chat/completions (claude-fast:haiku)
             → store {llm_purpose, llm_why, source='llm', model, evidence} in repo_llm_analysis
   → chips through all repos over many runs
```

- **Backend**: `claude-http:8765` (container `claude-http`, on nginx-network = same as
  homelab-status, reachable by name). Model `claude-fast:haiku`. OpenRouter fallback.
- **Resumable**: only analyzes repos not yet in `repo_llm_analysis` (unless `force=true`).
- **Provenance**: every result marked `source='llm'` + model + the code evidence it used
  (synthesis-discipline — inference is never presented as fact).

## ⚠️ Verification still owed (deferred, honestly)

Merged 2026-06-27 WITHOUT a live single-repo proof — both verification paths were
blocked at merge time (SSH fail2ban'd after heavy churn; public URL sandbox-blocked).
The code is tested (45 unit tests) and points at the proven claude-http gateway on a
shared network, but **LLM output QUALITY is unproven.** First real run proves it.

### Prove it after deploy (run on the host, or via the app once deployed)

```bash
# 1. confirm the new image is running (has repo_llm)
ssh homelab 'docker exec homelab-status python3 -c "import homelab_status.repo_llm; print(\"deployed\")"'

# 2. confirm the gateway answers from the container
ssh homelab 'docker exec homelab-status python3 -c "
import httpx; r=httpx.post(\"http://claude-http:8765/v1/chat/completions\",
 json={\"model\":\"claude-fast:haiku\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply: OK\"}]},timeout=60);
print(r.status_code, r.json()[\"choices\"][0][\"message\"][\"content\"][:40])"'

# 3. analyze ONE real thin-README repo + read the result
ssh homelab 'curl -s -X POST "http://localhost:8800/api/registry/analyze?limit=1"'
sleep 30
ssh homelab 'curl -s "http://localhost:8800/api/registry/analysis/CALL-CENTER" | python3 -m json.tool'
#   GOOD output (real purpose, not garbage) => the approach works => enable the cron
```

## Cron (enable AFTER step 3 proves good output)

On the Hetzner host (`crontab -e`), same pattern as the Terry orchestrator:

```cron
# LLM-analyze a small batch of repos every 15 min (resumable; ~claude-fast:haiku is fast)
*/15 * * * * curl -s -X POST 'http://localhost:8800/api/registry/analyze?limit=10' >/dev/null 2>&1
```

10 repos/15min → all ~133 covered in a few hours, then it idles (nothing new to analyze)
until repos change. Bump `limit` to go faster; claude-fast:haiku is seconds/repo, not minutes.

## If output is bad

- Try a stronger model: `ANALYSIS_MODEL=sonnet` (env on the container).
- The runner is resumable + idempotent; re-run with `force=true` to re-analyze.
