"""#14: consume the diagram server's live map (don't recompute). The join from
learning (repo) -> runtime (is it deployed/running) must work + fail honestly."""

from homelab_status import infra


def test_runtime_for_repo_exact_and_prefix_match():
    cmap = {
        "homelab-status": {"health": "running", "url": "http://x:8800"},
        "pete-db-api": {"health": "healthy", "url": "https://pete-db.x"},
    }
    # exact
    assert infra.runtime_for_repo(cmap, "homelab-status")["container"] == "homelab-status"
    # prefix (repo 'pete-db' deploys as container 'pete-db-api')
    m = infra.runtime_for_repo(cmap, "pete-db")
    assert m and m["container"] == "pete-db-api"
    # honest None when nothing matches — NOT a guess
    assert infra.runtime_for_repo(cmap, "Twilio_tools") is None


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
