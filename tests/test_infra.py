"""#14: consume the diagram server's live map (don't recompute). The join from
learning (repo) -> runtime (is it deployed/running) must work + fail honestly."""

from homelab_status import infra


def test_runtime_for_repo_matches_via_name_image_and_multi_container():
    cmap = {
        "homelab-status": {"health": "running", "image": "ghcr.io/x/homelab-status"},
        "pete-db-api": {"health": "healthy", "image": "pete-db-api"},
        # Twilio_tools deploys as MULTIPLE containers whose names differ from the
        # repo; the link is the compose-project name embedded in the image.
        "twilio-backend": {"health": "healthy", "image": "twilio-tools-twilio-backend"},
        "twilio-frontend": {"health": "healthy", "image": "twilio-tools-twilio-frontend"},
    }
    # exact name
    assert infra.runtime_for_repo(cmap, "homelab-status")["container"] == "homelab-status"
    # repo 'pete-db' -> container 'pete-db-api' (name prefix)
    assert infra.runtime_for_repo(cmap, "pete-db")["container"] == "pete-db-api"
    # repo 'Twilio_tools' -> 2 containers, matched via IMAGE (the bug Mark caught)
    m = infra.runtime_for_repo(cmap, "Twilio_tools")
    assert m is not None and m["container_count"] == 2
    assert set(m["containers"]) == {"twilio-backend", "twilio-frontend"}
    # still honest None when truly nothing matches
    assert infra.runtime_for_repo(cmap, "NopeRepo") is None


def test_container_runtime_parses_diagram_shape(monkeypatch):
    fake = {"projects": {"p1": {"containers": [
        {"name": "terry-backend", "health": "healthy", "url": "http://x",
         "public_url": "https://terry-backend.x", "ssl_enabled": True},
    ]}}}

    async def fake_get(path, ttl=120):
        return fake
    monkeypatch.setattr(infra, "_get", fake_get)

    import asyncio
    out = asyncio.run(infra.container_runtime())
    assert "terry-backend" in out
    assert out["terry-backend"]["health"] == "healthy"
    assert out["terry-backend"]["public_url"] == "https://terry-backend.x"


def test_summary_unavailable_is_honest(monkeypatch):
    async def fake_get(path, ttl=120):
        return None      # unreachable
    monkeypatch.setattr(infra, "_get", fake_get)
    import asyncio
    s = asyncio.run(infra.runtime_summary())
    assert s["available"] is False     # says so, doesn't fabricate


def test_friendly_urls_for_matches_repo_containers_and_auth():
    """The NPM friendly-name layer: repo -> friendly URLs + auth (Mark's point)."""
    proxies = [
        {"domains": ["twilio-tools.markcarpenter1.com"], "forward_host": "twilio-frontend",
         "forward_port": 3001, "ssl": True, "container": "twilio-frontend",
         "access_list_id": 1, "access_list": "Clerk"},
        {"domains": ["twilio-tools-api.markcarpenter1.com"], "forward_host": "twilio-backend",
         "forward_port": 8000, "ssl": True, "container": "twilio-backend", "access_list_id": 0},
        {"domains": ["grafana.markcarpenter1.com"], "forward_host": "grafana",
         "forward_port": 3000, "ssl": True, "container": "grafana"},
    ]
    urls = infra.friendly_urls_for(proxies, "Twilio_tools", ["twilio-frontend", "twilio-backend"])
    found = {u["url"] for u in urls}
    assert "https://twilio-tools.markcarpenter1.com" in found
    assert "https://twilio-tools-api.markcarpenter1.com" in found
    assert "https://grafana.markcarpenter1.com" not in found       # not this repo
    # auth surfaced from the access_list (Clerk) vs public
    clerk = [u for u in urls if u["url"].endswith("twilio-tools.markcarpenter1.com")][0]
    assert clerk["auth"] == "Clerk"


def test_network_alignment_aligned_misaligned_unknown(monkeypatch):
    """Mark's docker-networking model: NPM forward_host must share a network with
    the proxy, or it's MISALIGNED ('Connection failed' despite healthy container).
    Must NOT false-flag (the shell-grep bug); uses set intersection."""
    monkeypatch.setattr(infra, "_container_networks", lambda: {
        "nginx-proxy-manager": {"nginx-network", "pete-network"},
        "twilio-backend": {"nginx-network", "twilio-network"},   # shares nginx -> aligned
        "lonely": {"isolated-network"},                          # no overlap -> MISALIGNED
    })

    async def fake_npm():
        return [
            {"domains": ["api.x"], "forward_host": "twilio-backend", "forward_port": 8000},
            {"domains": ["lonely.x"], "forward_host": "lonely", "forward_port": 9000},
            {"domains": ["ext.x"], "forward_host": "localhost", "forward_port": 8000},  # unknown
        ]
    monkeypatch.setattr(infra, "npm_proxies", fake_npm)

    import asyncio
    rows = {r["forward_host"]: r["status"] for r in asyncio.run(infra.network_alignment())}
    assert rows["twilio-backend"] == "aligned"
    assert rows["lonely"] == "MISALIGNED"
    assert rows["localhost"] == "unknown"        # not a container — honest, not 'broken'
