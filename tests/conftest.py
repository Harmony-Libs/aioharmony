"""Shared pytest fixtures for the aioharmony test suite."""

from __future__ import annotations

import ssl
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from blockbuster import BlockBuster, BlockBusterFunction, blockbuster_ctx

_SSL_CONTEXT_BLOCKING_FUNCS = (
    "load_default_certs",
    "load_verify_locations",
    "load_cert_chain",
    "set_default_verify_paths",
)


@pytest.fixture(autouse=True)
def blockbuster() -> Iterator[BlockBuster]:
    """Fail any test that makes a blocking call from inside the event loop."""
    # Stock blockbuster only patches SSLSocket read/write; the SSLContext
    # loaders do hidden file I/O and CPU-bound cert parsing too.
    ssl_context_functions = [
        BlockBusterFunction(ssl.SSLContext, func_name, scanned_modules="aioharmony")
        for func_name in _SSL_CONTEXT_BLOCKING_FUNCS
    ]
    with blockbuster_ctx("aioharmony") as bb:
        for ssl_fn in ssl_context_functions:
            ssl_fn.activate()
        try:
            yield bb
        finally:
            for ssl_fn in ssl_context_functions:
                ssl_fn.deactivate()


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
    client.set_sleep_timer = AsyncMock(return_value=True)
    client.sync = AsyncMock(return_value=True)
    client.get_device_id = MagicMock(return_value="dev42")
    client.get_device_name = MagicMock(return_value="TV")
    client.get_activity_id = MagicMock(return_value="9001")
    client.register_handler = MagicMock()
    return client
