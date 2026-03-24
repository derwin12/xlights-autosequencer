"""Centralized logging for xlight-analyze — writes to ~/.xlight/logs/."""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path


def get_logger(name: str = "xlight") -> logging.Logger:
    """Return a logger that writes to ~/.xlight/logs/xlight.log.

    Creates the log directory and file handler on first call.
    Subsequent calls for the same *name* return the cached logger.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    log_dir = Path.home() / ".xlight" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "xlight.log"

    handler = logging.FileHandler(str(log_file), encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(name)-24s  %(levelname)-7s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    level = os.environ.get("XLIGHT_LOG_LEVEL", "DEBUG").upper()
    logger.setLevel(getattr(logging, level, logging.DEBUG))
    handler.setLevel(logging.DEBUG)
    logger.addHandler(handler)

    return logger
