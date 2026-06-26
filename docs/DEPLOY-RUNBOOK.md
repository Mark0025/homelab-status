# Deploy runbook — homelab-status (#19)

> How code reaches Hetzner. After the one-time setup below, **merge to main = live within ~5 min** (Watchtower auto-pull). Until then, deploy is manual.

## The pipeline (recap)

```
PR → squash to main → GitHub Actions build-and-push → ghcr.io/mark0025/homelab-status:latest
   → Watchtower on Hetzner polls (5 min) → pulls new :latest → restarts ONLY homelab-status
```

## ⚠️ Root issue this fixes (proven 2026-06-25)

The live container was created from **`/home/mark/homelab-status/`** — a directory whose `.env` has **no GitHub token**. The correct `.env` (with the token) is in **`/home/mark/00Myhomelab/homelab-status/`**. That empty token is why git ingestion was stuck at 1 commit (#20). There are duplicate compose dirs; the `00Myhomelab` one is canonical.

## One-time host setup (run as `mark` on Hetzner — needs your token + a decision)

```bash
ssh homelab

# 1. Stop the WRONG-directory container (the tokenless one).
cd /home/mark/homelab-status && docker compose down

# 2. Go to the CANONICAL dir (has the token .env) and pull the latest compose.
cd /home/mark/00Myhomelab/homelab-status
git pull            # gets the new docker-compose.yml with Watchtower + label

# 3. Confirm the token is present (should print a non-zero length, NOT the token).
grep -c GITHUB_PERSONAL_ACCESS_TOKEN .env     # expect: 1
#   (do NOT cat the .env in a shared session)

# 4. Bring up homelab-status + the scoped Watchtower.
docker compose up -d

# 5. Verify the container is from the RIGHT dir now + has the token.
docker inspect homelab-status --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}'
#   expect: /home/mark/00Myhomelab/homelab-status
docker exec homelab-status sh -lc 'echo TOKEN_LEN=${#GITHUB_PERSONAL_ACCESS_TOKEN}'
#   expect: TOKEN_LEN=<non-zero>

# 6. Force a git refresh and confirm ingestion is fixed (1 -> 23 for homelab-status).
curl -s -X POST 'http://localhost:8800/api/git/refresh?force=true' >/dev/null
sleep 20
curl -s http://localhost:8800/api/intel/profiles | grep -o '"repo":"homelab-status"[^}]*total_commits":[0-9]*'
#   expect total_commits > 1 (the real count)
```

## Optional cleanup (your call — the 3-dir mess)

There are stray homelab-status dirs. Once the canonical `00Myhomelab` one is confirmed live, the duplicate at `/home/mark/homelab-status/` can be removed so a future deploy can't pick the wrong one again. **Verify before deleting** (LEGO rule — don't delete what you didn't confirm):
```bash
docker inspect homelab-status --format '{{ index .Config.Labels "com.docker.compose.project.config_files" }}'
# must NOT point at /home/mark/homelab-status before you rm it
```

## Why scoped Watchtower (not host-wide)

This host runs **~106 containers** (Terry, Pete, NPM, …). A default Watchtower auto-updates EVERY container with a `:latest` tag — a huge, surprising blast radius. The compose here runs Watchtower with `WATCHTOWER_LABEL_ENABLE=true`, and only homelab-status carries `com.centurylinklabs.watchtower.enable=true`. So Watchtower touches **exactly one container**. The other ~105 are untouched.

## Verifying auto-deploy works (after setup)

```bash
docker logs watchtower-homelab-status --tail 20    # should show it scanning + 'Found 1 container to watch'
# Then merge any PR → within ~5 min, homelab-status restarts on the new image:
docker inspect homelab-status --format '{{.Image}}'   # SHA changes after an update
```

## Rollback

Watchtower only moves forward. To pin/rollback: `docker compose down`, set the image to a specific `sha-XXXX` tag in compose (GitHub Actions tags every build), `docker compose up -d`. Remove the watchtower label temporarily if you want to freeze.
