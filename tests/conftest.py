"""Shared pytest fixtures for the aioharmony test suite."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_client() -> MagicMock:
    """Return a ``MagicMock`` standing in for ``HarmonyAPI``."""
    client = MagicMock(name="HarmonyAPI")
    client.name = "Living Room"
    client.fw_version = "4.15.250"
    client.hub_id = "abc123"
    client.protocol = "WEBSOCKETS"
    client.config = {"some": "config"}
    client.json_config = {"some": "config"}
    client.hub_config = {"detailed": "config"}
    client.current_activity = (42, "Watch TV")
    client.callbacks = MagicMock(config_updated="cu", connect="c", disconnect="d")
    client.connect = AsyncMock(return_value=True)
    client.close = AsyncMock(return_value=None)
    client.power_off = AsyncMock(return_value=True)
    client.start_activity = AsyncMock(return_value=(True, "ok"))
    client.send_commands = AsyncMock(return_value=[])
    client.change_channel = AsyncMock(return_value=True)
    client.sync = AsyncMock(return_value=True)
    client.get_device_id = MagicMock(return_value="dev42")
    client.get_device_name = MagicMock(return_value="TV")
    client.get_activity_id = MagicMock(return_value="9001")
    client.register_handler = MagicMock()
    return client
