"""Tests for logging configuration."""
import logging
import os
from pathlib import Path

import logging_config as lc
from config import settings


def test_configure_logging_sets_console_and_rotating_file_handlers(tmp_path):
    """Logging config should install both console and rotating file handlers."""
    original_log_dir = settings.log_dir
    original_file_name = settings.log_file_name
    original_level = settings.log_level
    original_max = settings.log_max_bytes
    original_backups = settings.log_backup_count

    try:
        settings.log_dir = tmp_path
        settings.log_file_name = "app-test.log"
        settings.log_level = "DEBUG"
        settings.log_max_bytes = 1024
        settings.log_backup_count = 2
        lc._LOGGING_CONFIGURED = False

        lc.configure_logging()

        root = logging.getLogger()
        handler_types = {type(handler).__name__ for handler in root.handlers}
        assert "StreamHandler" in handler_types
        assert "RotatingFileHandler" in handler_types
        assert (tmp_path / "app-test.log").exists()
    finally:
        settings.log_dir = original_log_dir
        settings.log_file_name = original_file_name
        settings.log_level = original_level
        settings.log_max_bytes = original_max
        settings.log_backup_count = original_backups
        lc._LOGGING_CONFIGURED = False


def test_configure_logging_falls_back_to_info_for_invalid_level(tmp_path):
    """Invalid LOG_LEVEL should fall back to INFO."""
    original_log_dir = settings.log_dir
    original_file_name = settings.log_file_name
    original_level = settings.log_level
    try:
        settings.log_dir = tmp_path
        settings.log_file_name = "invalid-level.log"
        settings.log_level = "NOT_A_LEVEL"
        lc._LOGGING_CONFIGURED = False

        lc.configure_logging()

        assert logging.getLogger().level == logging.INFO
    finally:
        settings.log_dir = original_log_dir
        settings.log_file_name = original_file_name
        settings.log_level = original_level
        lc._LOGGING_CONFIGURED = False


def test_configure_logging_skips_file_handler_in_reload_mode(tmp_path):
    """Reload mode should skip file handler by default to avoid reload loops."""
    original_log_dir = settings.log_dir
    original_file_name = settings.log_file_name
    original_reload_flag = settings.log_to_file_in_reload
    original_watchfiles = os.environ.get("WATCHFILES_CHANGES")
    try:
        settings.log_dir = tmp_path
        settings.log_file_name = "reload.log"
        settings.log_to_file_in_reload = False
        os.environ["WATCHFILES_CHANGES"] = "1"
        lc._LOGGING_CONFIGURED = False

        lc.configure_logging()

        root = logging.getLogger()
        handler_types = {type(handler).__name__ for handler in root.handlers}
        assert "RotatingFileHandler" not in handler_types
    finally:
        settings.log_dir = original_log_dir
        settings.log_file_name = original_file_name
        settings.log_to_file_in_reload = original_reload_flag
        if original_watchfiles is None:
            os.environ.pop("WATCHFILES_CHANGES", None)
        else:
            os.environ["WATCHFILES_CHANGES"] = original_watchfiles
        lc._LOGGING_CONFIGURED = False


def test_configure_logging_quiets_watchfiles_noise():
    """watchfiles internal change spam should be suppressed to WARNING."""
    lc._LOGGING_CONFIGURED = False
    lc.configure_logging()
    assert logging.getLogger("watchfiles.main").level == logging.WARNING
    lc._LOGGING_CONFIGURED = False
