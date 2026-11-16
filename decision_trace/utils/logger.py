"""
Structured console logging with Rich.

Usage:
    from decision_trace.utils.logger import get_logger
    log = get_logger(__name__)
    log.info("Pipeline started")
"""
from __future__ import annotations

import logging

from rich.logging import RichHandler

from config.settings import settings

_configured: bool = False


def _configure_root() -> None:
    global _configured
    if _configured:
        return
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, show_path=True)],
    )
    _configured = True


def get_logger(name: str) -> logging.Logger:
    _configure_root()
    return logging.getLogger(name)
