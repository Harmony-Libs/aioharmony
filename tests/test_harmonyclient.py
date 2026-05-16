"""Tests for HarmonyClient synchronous helpers and lifecycle paths."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

import aioharmony.exceptions as aioexc
from aioharmony.const import (
    WEBSOCKETS,
    XMPP,
    ClientCallbackType,
)
from aioharmony.harmonyclient import HarmonyClient

pytestmark = pytest.mark.asyncio


def _make_callbacks(**overrides: Any) -> ClientCallbackType:
    fields: dict[str, Any] = {
        "connect": None,
        "disconnect": None,
        "new_activity_starting": None,
        "new_activity": None,
        "config_updated": None,
    }
    fields.update(overrides)
    return ClientCallbackType(**fields)


def _make_client(**kwargs: Any) -> HarmonyClient:
    """Construct a HarmonyClient with a default IP — must be called inside a loop."""
    kwargs.setdefault("ip_address", "10.0.0.42")
    return HarmonyClient(**kwargs)


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[HarmonyClient]:
    c = _make_client()
    real_handler = c._callback_handler  # noqa: SLF001
    yield c
    # Tests sometimes swap _callback_handler for a MagicMock; keep a reference
    # to the real one so the background task spawned by ResponseHandler.__init__
    # gets cancelled on teardown.
    await real_handler.close()


@pytest_asyncio.fixture
async def populated_client(client: HarmonyClient) -> HarmonyClient:
    client._hub_config = client._hub_config._replace(  # noqa: SLF001
        activities=[
            {"id": 1, "name": "Watch TV", "name_lowercase": "watch tv"},
            {"id": 2, "name": "Listen Music", "name_lowercase": "listen music"},
        ],
        devices=[
            {"id": 100, "name": "TV", "name_lowercase": "tv"},
            {"id": 200, "name": "Receiver", "name_lowercase": "receiver"},
        ],
    )
    return client


# ---------------------------------------------------------------------------
# __init__ and properties
# ---------------------------------------------------------------------------


async def test_init_default_populates_state() -> None:
    c = _make_client(ip_address="10.0.0.1")
    try:
        assert c.ip_address == "10.0.0.1"
        assert c.protocol is None
        assert c.current_activity_id is None
        assert c.hub_config.config == {}
        assert c.hub_config.activities == []
        assert c.hub_config.devices == []
        assert c.hub_config.config_version is None
        assert c.callbacks == ClientCallbackType(None, None, None, None, None)
    finally:
        await c._callback_handler.close()  # noqa: SLF001


async def test_init_accepts_custom_callbacks() -> None:
    cbs = _make_callbacks(connect=MagicMock(), disconnect=MagicMock())
    c = _make_client(callbacks=cbs)
    try:
        assert c.callbacks is cbs
    finally:
        await c._callback_handler.close()  # noqa: SLF001


async def test_init_accepts_protocol_override() -> None:
    c = _make_client(protocol=XMPP)
    try:
        assert c.protocol == XMPP
    finally:
        await c._callback_handler.close()  # noqa: SLF001


async def test_init_uses_running_loop_when_no_loop_given() -> None:
    c = _make_client()
    try:
        assert c._loop is asyncio.get_running_loop()  # noqa: SLF001
    finally:
        await c._callback_handler.close()  # noqa: SLF001


async def test_name_falls_back_to_ip_when_no_friendly_name(
    client: HarmonyClient,
) -> None:
    assert client.name == "10.0.0.42"


async def test_name_returns_friendly_name_when_present(
    client: HarmonyClient,
) -> None:
    client._hub_config = client._hub_config._replace(  # noqa: SLF001
        discover_info={"friendlyName": "Den"}
    )
    assert client.name == "Den"


async def test_init_registers_core_handlers_on_response_handler(
    client: HarmonyClient,
) -> None:
    # 4 core handlers are registered in __init__:
    # START_ACTIVITY_FINISHED, START_ACTIVITY_NOTIFY_STARTED,
    # STOP_ACTIVITY_NOTIFY_STARTED, NOTIFY.
    assert len(client._callback_handler._handler_list) == 4  # noqa: SLF001


# ---------------------------------------------------------------------------
# callbacks setter
# ---------------------------------------------------------------------------


async def test_callbacks_setter_updates_and_propagates(
    client: HarmonyClient,
) -> None:
    fake_conn = MagicMock()
    client._hub_connection = fake_conn  # noqa: SLF001

    new_cbs = _make_callbacks(
        connect=MagicMock(name="cn"), disconnect=MagicMock(name="dc")
    )
    client.callbacks = new_cbs

    assert client.callbacks is new_cbs
    assert fake_conn.callbacks.connect is new_cbs.connect
    assert fake_conn.callbacks.disconnect is new_cbs.disconnect


# ---------------------------------------------------------------------------
# lookups: get_activity_id / get_activity_name / get_device_id / get_device_name
# ---------------------------------------------------------------------------


async def test_get_activity_id_match(populated_client: HarmonyClient) -> None:
    assert populated_client.get_activity_id("Watch TV") == 1


async def test_get_activity_id_case_insensitive(
    populated_client: HarmonyClient,
) -> None:
    assert populated_client.get_activity_id("WATCH tv") == 1


async def test_get_activity_id_none_when_unknown(
    populated_client: HarmonyClient,
) -> None:
    assert populated_client.get_activity_id("Sleep") is None


async def test_get_activity_id_none_when_input_none(
    populated_client: HarmonyClient,
) -> None:
    assert populated_client.get_activity_id(None) is None


async def test_get_activity_name_match(populated_client: HarmonyClient) -> None:
    assert populated_client.get_activity_name(2) == "Listen Music"


async def test_get_activity_name_accepts_string_id(
    populated_client: HarmonyClient,
) -> None:
    assert populated_client.get_activity_name("2") == "Listen Music"


async def test_get_activity_name_none_when_unknown(
    populated_client: HarmonyClient,
) -> None:
    assert populated_client.get_activity_name(999) is None


async def test_get_activity_name_none_when_input_none(
    populated_client: HarmonyClient,
) -> None:
    assert populated_client.get_activity_name(None) is None


async def test_get_device_id_match(populated_client: HarmonyClient) -> None:
    assert populated_client.get_device_id("TV") == 100


async def test_get_device_id_none_when_unknown(
    populated_client: HarmonyClient,
) -> None:
    assert populated_client.get_device_id("Toaster") is None


async def test_get_device_id_none_when_input_none(
    populated_client: HarmonyClient,
) -> None:
    assert populated_client.get_device_id(None) is None


async def test_get_device_name_match(populated_client: HarmonyClient) -> None:
    assert populated_client.get_device_name(200) == "Receiver"


async def test_get_device_name_accepts_string_id(
    populated_client: HarmonyClient,
) -> None:
    assert populated_client.get_device_name("200") == "Receiver"


async def test_get_device_name_none_when_unknown(
    populated_client: HarmonyClient,
) -> None:
    assert populated_client.get_device_name(999) is None


async def test_get_device_name_none_when_input_none(
    populated_client: HarmonyClient,
) -> None:
    assert populated_client.get_device_name(None) is None


# ---------------------------------------------------------------------------
# register_handler / unregister_handler delegation
# ---------------------------------------------------------------------------


async def test_register_handler_delegates(client: HarmonyClient) -> None:
    client._callback_handler = MagicMock()  # noqa: SLF001
    client._callback_handler.register_handler.return_value = "uuid-1"  # noqa: SLF001
    result = client.register_handler("a", b=1)
    assert result == "uuid-1"
    client._callback_handler.register_handler.assert_called_once_with("a", b=1)  # noqa: SLF001


async def test_unregister_handler_delegates(client: HarmonyClient) -> None:
    client._callback_handler = MagicMock()  # noqa: SLF001
    client._callback_handler.unregister_handler.return_value = True  # noqa: SLF001
    result = client.unregister_handler("uuid-1")
    assert result is True
    client._callback_handler.unregister_handler.assert_called_once_with("uuid-1")  # noqa: SLF001


# ---------------------------------------------------------------------------
# _websocket_or_xmpp transport selection
# ---------------------------------------------------------------------------


async def test_websocket_or_xmpp_selects_websockets_when_probe_succeeds(
    client: HarmonyClient,
) -> None:
    with (
        patch(
            "aioharmony.harmonyclient.asyncio.open_connection",
            new=AsyncMock(return_value=(MagicMock(), MagicMock())),
        ),
        patch("aioharmony.hubconnector_websocket.HubConnector") as ws_connector,
    ):
        ok = await client._websocket_or_xmpp()  # noqa: SLF001
    assert ok is True
    assert client.protocol == WEBSOCKETS
    ws_connector.assert_called_once()


async def test_websocket_or_xmpp_falls_back_to_xmpp_on_connection_refused(
    client: HarmonyClient,
) -> None:
    with (
        patch(
            "aioharmony.harmonyclient.asyncio.open_connection",
            new=AsyncMock(side_effect=ConnectionRefusedError),
        ),
        patch("aioharmony.hubconnector_xmpp.HubConnector") as xmpp_connector,
    ):
        ok = await client._websocket_or_xmpp()  # noqa: SLF001
    assert ok is True
    assert client.protocol == XMPP
    xmpp_connector.assert_called_once()


async def test_websocket_or_xmpp_returns_false_on_oserror_with_unknown_protocol(
    client: HarmonyClient,
) -> None:
    with patch(
        "aioharmony.harmonyclient.asyncio.open_connection",
        new=AsyncMock(side_effect=OSError),
    ):
        ok = await client._websocket_or_xmpp()  # noqa: SLF001
    assert ok is False
    assert client.protocol is None


async def test_websocket_or_xmpp_skips_probe_when_protocol_is_explicit_xmpp(
    client: HarmonyClient,
) -> None:
    client._protocol = XMPP  # noqa: SLF001
    with (
        patch(
            "aioharmony.harmonyclient.asyncio.open_connection", new=AsyncMock()
        ) as probe,
        patch("aioharmony.hubconnector_xmpp.HubConnector") as xmpp_connector,
    ):
        ok = await client._websocket_or_xmpp()  # noqa: SLF001
    assert ok is True
    assert client.protocol == XMPP
    probe.assert_not_called()
    xmpp_connector.assert_called_once()


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


async def test_close_with_no_hub_connection_closes_callback_handler(
    client: HarmonyClient,
) -> None:
    client._hub_connection = None  # noqa: SLF001
    # Replace callback_handler after init so we don't double-close in teardown.
    client._callback_handler = MagicMock()  # noqa: SLF001
    client._callback_handler.close = AsyncMock()  # noqa: SLF001

    await client.close()

    client._callback_handler.close.assert_awaited_once()  # noqa: SLF001


async def test_close_closes_hub_connection_and_handler(
    client: HarmonyClient,
) -> None:
    client._hub_connection = MagicMock()  # noqa: SLF001
    client._hub_connection.close = AsyncMock()  # noqa: SLF001
    client._callback_handler = MagicMock()  # noqa: SLF001
    client._callback_handler.close = AsyncMock()  # noqa: SLF001

    await client.close()

    client._hub_connection.close.assert_awaited_once()  # noqa: SLF001
    client._callback_handler.close.assert_awaited_once()  # noqa: SLF001


async def test_close_propagates_hub_connection_exception(
    client: HarmonyClient,
) -> None:
    client._hub_connection = MagicMock()  # noqa: SLF001
    client._hub_connection.close = AsyncMock(side_effect=RuntimeError("boom"))  # noqa: SLF001
    client._callback_handler = MagicMock()  # noqa: SLF001
    client._callback_handler.close = AsyncMock()  # noqa: SLF001

    with pytest.raises(RuntimeError, match="boom"):
        await client.close()

    client._callback_handler.close.assert_awaited_once()  # noqa: SLF001


async def test_close_converts_hub_timeout_to_aiotimeout(
    client: HarmonyClient,
) -> None:
    client._hub_connection = MagicMock()  # noqa: SLF001
    client._hub_connection.close = AsyncMock(side_effect=asyncio.TimeoutError)  # noqa: SLF001
    client._callback_handler = MagicMock()  # noqa: SLF001
    client._callback_handler.close = AsyncMock()  # noqa: SLF001

    with pytest.raises(aioexc.TimeOut):
        await client.close()

    client._callback_handler.close.assert_awaited_once()  # noqa: SLF001


async def test_close_raises_when_callback_handler_times_out(
    client: HarmonyClient,
) -> None:
    client._hub_connection = None  # noqa: SLF001
    client._callback_handler = MagicMock()  # noqa: SLF001
    client._callback_handler.close = AsyncMock(side_effect=asyncio.TimeoutError)  # noqa: SLF001

    with pytest.raises(aioexc.TimeOut):
        await client.close()

    client._callback_handler.close.assert_awaited_once()  # noqa: SLF001


# ---------------------------------------------------------------------------
# disconnect
# ---------------------------------------------------------------------------


async def test_disconnect_delegates_to_hub_connection(
    client: HarmonyClient,
) -> None:
    client._hub_connection = MagicMock()  # noqa: SLF001
    client._hub_connection.hub_disconnect = AsyncMock()  # noqa: SLF001

    await client.disconnect()

    client._hub_connection.hub_disconnect.assert_awaited_once()  # noqa: SLF001


async def test_disconnect_converts_timeout_to_aiotimeout(
    client: HarmonyClient,
) -> None:
    client._hub_connection = MagicMock()  # noqa: SLF001
    client._hub_connection.hub_disconnect = AsyncMock(  # noqa: SLF001
        side_effect=asyncio.TimeoutError
    )

    with pytest.raises(aioexc.TimeOut):
        await client.disconnect()
