"""Issue #22: both entrypoints must configure loguru (the container ran with
the default unconfigured sink before this)."""

from homelab_status import logging_config


def test_configure_logging_is_idempotent_and_returns_level(monkeypatch):
    logging_config._configured = False
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    assert logging_config.configure_logging() == "INFO"
    # second call is a no-op but still returns the resolved level
    assert logging_config.configure_logging() == "INFO"


def test_env_level_is_respected(monkeypatch):
    logging_config._configured = False
    monkeypatch.setenv("LOG_LEVEL", "debug")
    assert logging_config.configure_logging() == "DEBUG"


def test_explicit_level_overrides_env(monkeypatch):
    logging_config._configured = False
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    assert logging_config.configure_logging(level="WARNING", force=True) == "WARNING"


def test_importing_web_configures_logging(monkeypatch):
    """Importing the FastAPI module must leave logging configured (the prod path)."""
    logging_config._configured = False
    import importlib

    from homelab_status import web

    importlib.reload(web)  # re-run module-level configure_logging()
    assert logging_config._configured is True
