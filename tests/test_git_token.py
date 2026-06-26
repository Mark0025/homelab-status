"""Regression tests for issue #20: a missing GitHub token must FAIL LOUD,
not silently send `Authorization: Bearer ` and ingest 0 commits."""

import pytest

from homelab_status import git_history as g


def _clear_token(monkeypatch):
    monkeypatch.delenv("GITHUB_PERSONAL_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    # Stop the gh-CLI fallback from finding a token on the dev machine.
    monkeypatch.setattr(g, "_token_from_gh_cli", lambda: "")


def test_github_headers_raises_when_token_missing(monkeypatch):
    _clear_token(monkeypatch)
    with pytest.raises(RuntimeError, match="No GitHub token"):
        g._github_headers()


def test_github_headers_ok_when_token_present(monkeypatch):
    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "ghp_dummy")
    headers = g._github_headers()
    assert headers["Authorization"] == "Bearer ghp_dummy"


@pytest.mark.asyncio
async def test_refresh_all_aborts_loudly_without_token(monkeypatch):
    """refresh_all must return an error status (not silently fetch 0) when no token."""
    _clear_token(monkeypatch)
    result = await g.refresh_all(force=True)
    assert result["status"] == "error"
    assert result["error"] == "no_github_token"
    assert result["commits_saved"] == 0


def test_resolve_token_strips_and_prefers_env(monkeypatch):
    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "  ghp_padded  ")
    assert g._resolve_token() == "ghp_padded"


@pytest.mark.asyncio
async def test_refresh_prs_aborts_loudly_without_token(monkeypatch):
    """PR ingestion must also fail loud on missing token (#20 class, PR path)."""
    from homelab_status import timeline as tl
    _clear_token(monkeypatch)
    result = await tl.refresh_prs()
    assert result.get("status") == "error"
    assert result.get("error") == "no_github_token"
    assert result.get("prs_saved") == 0
