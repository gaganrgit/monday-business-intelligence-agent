"""
Centralized logging configuration.

Uses Python's built-in logging module only (no external logging
libraries) to keep the stack simple, as required by the assignment.
"""

import logging
import sys
from backend.app.config import settings


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger instance for the given module name."""
    logger = logging.getLogger(name)

    if not logger.handlers:
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(settings.log_level or "INFO")
        logger.propagate = False

    return logger
