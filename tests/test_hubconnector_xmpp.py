"""Tests for the slixmpp connector."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
import slixmpp

from aioharmony.const import ConnectorCallbackType
from aioharmony.hubconnector_xmpp import HubConnector


@pytest.mark.asyncio
async def test_hub_connect_uses_modern_slixmpp_kwargs() -> None:
    """hub_connect must call ClientXMPP.connect with host=/port=.

    Regression for issue #93: slixmpp 1.10 replaced address=/disable_starttls=
    /use_ssl= with host=/port= and instance-level TLS toggles. The old call
    shape raises TypeError on any modern slixmpp.
    """
    queue: asyncio.Queue = asyncio.Queue()
    hub = HubConnector(
        ip_address="10.0.0.42",
        response_queue=queue,
        callbacks=ConnectorCallbackType(None, None),
    )

    captured: dict = {}

    def fake_connect(self: slixmpp.ClientXMPP, *args: object, **kwargs: object) -> None:
        captured["args"] = args
        captured["kwargs"] = kwargs
        # Drive the "connected" event so hub_connect's awaited future resolves.
        loop = asyncio.get_running_loop()
        loop.call_soon(self.event, "connected", None)

    with patch.object(slixmpp.ClientXMPP, "connect", fake_connect):
        result = await hub.hub_connect()

    assert result is True
    assert captured["args"] == ()
    assert captured["kwargs"] == {"host": "10.0.0.42", "port": 5222}
    # Harmony Hubs speak plain XMPP on the LAN; both TLS toggles must be off.
    assert hub.enable_starttls is False
    assert hub.enable_direct_tls is False

    await hub.hub_disconnect()
