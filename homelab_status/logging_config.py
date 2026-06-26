"""Shared loguru configuration for BOTH entrypoints (CLI + FastAPI container).

Before this module, logging was configured only in main.py's CLI path, so the
running container (uvicorn web.py) used loguru's unconfigured default sink —
unstructured, no level control, interleaved with raw uvicorn lines. (Issue #22.)

Call `configure_logging()` from each entrypoint. Level is env-driven
(LOG_LEVEL, default INFO) so the container can be tuned without a code change.
"""

import os
import sys

from loguru import logger

_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level:<8}</level> | "
    "<cyan>{name}:{function}:{line}</cyan> | {message}"
)

_configured = False


def configure_logging(level: str | None = None, *, force: bool = False) -> str:
    """Install a single stderr sink. Idempotent — safe to call from import-time
    in web.py AND from the CLI. Returns the resolved level.

    `level` overrides the env; otherwise LOG_LEVEL, otherwise INFO.
    """
    global _configured
    resolved = (level or os.environ.get("LOG_LEVEL") or "INFO").upper()
    if _configured and not force:
        return resolved
    logger.remove()
    logger.add(
        sys.stderr,
        level=resolved,
        format=_FORMAT,
        colorize=True,
        backtrace=False,
        diagnose=False,
    )
    _configured = True
    return resolved
