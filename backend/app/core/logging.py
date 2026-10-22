"""Structured logging configuration for VENORA AI."""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from app.core.config import Settings, get_settings

_LOGGING_INITIALIZED = False


def setup_logging(settings: Optional[Settings] = None) -> logging.Logger:
    """Configure root logger with console and rotating file handlers."""
    global _LOGGING_INITIALIZED

    if settings is None:
        settings = get_settings()

    logger = logging.getLogger("venora")

    # Avoid duplicate handlers during test runs or uvicorn hot-reloads
    if _LOGGING_INITIALIZED:
        return logger

    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(log_level)
    logger.propagate = False

    # Format: [2026-10-22 10:00:00,000] [INFO] [venora.api.routes.health] Message
    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Clear existing handlers if any
    if logger.hasHandlers():
        logger.handlers.clear()

    # 1. Console Handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 2. Rotating File Handler
    try:
        log_dir = Path(settings.LOG_DIR)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file_path = log_dir / settings.LOG_FILE_NAME

        file_handler = RotatingFileHandler(
            filename=str(log_file_path),
            maxBytes=settings.LOG_MAX_BYTES,
            backupCount=settings.LOG_BACKUP_COUNT,
            encoding="utf-8"
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as exc:
        # Fallback to console only if file access fails (e.g. read-only env)
        logger.warning(f"Could not initialize rotating file logger: {exc}")

    _LOGGING_INITIALIZED = True
    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a child logger inheriting VENORA logging configuration."""
    return logging.getLogger(f"venora.{name}")
