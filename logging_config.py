"""Centralized logging configuration for the karaoke application."""
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import settings

_LOGGING_CONFIGURED = False


def _resolve_level(level_name: str) -> int:
    candidate = str(level_name or "").upper()
    level_value = getattr(logging, candidate, None)
    if isinstance(level_value, int):
        return level_value
    return logging.INFO


def _running_under_reload_mode() -> bool:
    """Best-effort detection for development reload mode."""
    return (
        os.environ.get("KARAOKE_RELOAD_ACTIVE") == "1"
        or "WATCHFILES_CHANGES" in os.environ
    )


def configure_logging() -> None:
    """Configure root logging with console and rotating file handlers."""
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    settings.ensure_paths()
    level = _resolve_level(settings.log_level)
    formatter = logging.Formatter(settings.log_format)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    if settings.log_to_file_in_reload or not _running_under_reload_mode():
        log_file_path = Path(settings.log_dir) / settings.log_file_name
        file_handler = RotatingFileHandler(
            filename=log_file_path,
            maxBytes=settings.log_max_bytes,
            backupCount=settings.log_backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.setLevel(level)
        uvicorn_logger.propagate = True
        uvicorn_logger.handlers.clear()

    # watchfiles can emit high-frequency "N changes detected" logs during reload.
    # Keep reload notices from uvicorn, but suppress watchfiles internal chatter.
    logging.getLogger("watchfiles.main").setLevel(logging.WARNING)

    _LOGGING_CONFIGURED = True
