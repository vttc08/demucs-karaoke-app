"""Tests for the main server entrypoint."""

from pathlib import Path

import main


def test_build_uvicorn_run_kwargs_sets_reload_and_shutdown_timeout():
    """The dev server should reload and exit within a bounded shutdown window."""
    original_log_dir = main.settings.log_dir
    original_host = main.settings.host
    original_port = main.settings.port

    try:
        main.settings.log_dir = Path("server-logs")
        main.settings.host = "127.0.0.1"
        main.settings.port = 8123

        kwargs = main.build_uvicorn_run_kwargs()

        assert kwargs["host"] == "127.0.0.1"
        assert kwargs["port"] == 8123
        assert kwargs["reload"] is True
        assert kwargs["timeout_graceful_shutdown"] == 3
        assert ".venv" in kwargs["reload_excludes"]
        assert "server-logs" in kwargs["reload_excludes"]
        assert "*.log" in kwargs["reload_excludes"]
    finally:
        main.settings.log_dir = original_log_dir
        main.settings.host = original_host
        main.settings.port = original_port
