"""Pytest configuration."""
import sys
from pathlib import Path

import pytest

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(autouse=True)
def fast_websocket_heartbeat():
    """Keep WebSocket integration tests from waiting on the production heartbeat interval."""
    from config import settings

    original_interval = settings.ws_heartbeat_interval
    settings.ws_heartbeat_interval = 1
    try:
        yield
    finally:
        settings.ws_heartbeat_interval = original_interval

