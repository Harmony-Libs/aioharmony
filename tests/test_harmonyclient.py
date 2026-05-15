"""Tests for HarmonyClient synchronous helpers and lifecycle paths."""

from __future__ import annotations

import asyncio
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


def _make_callbacks(**overrides) -> ClientCallbackType:
    fields = {
        "connect": None,
        "disconnect": None,
        "new_activity_starting": None,
        "new_activity": None,
        "config_updated": None,
    }
    fields.update(overrides)
    return ClientCallbackType(**fields)


async def _make_client(**kwargs) -> HarmonyClient:
    """HarmonyClient.__init__ creates asyncio primitives — needs a running loop."""
    kwargs.setdefault("ip_address", "10.0.0.42")
    return HarmonyClient(**kwargs)


@pytest_asyncio.fixture
async def client() -> HarmonyClient:
    c = await _make_client()
    real_handler = c._callback_handler  # noqa: SLF001
    yield c
    # Tests sometimes swap _callback_handler for a MagicMock; restore so the
    # background task spawned by ResponseHandler.__init__ gets cancelled.
    await real_handler.close()


class TestInitAndProperties:
    async def test_default_init_populates_state(self) -> None:
        c = await _make_client(ip_address="10.0.0.1")
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

    async def test_init_accepts_custom_callbacks(self) -> None:
        cbs = _make_callbacks(connect=MagicMock(), disconnect=MagicMock())
        c = await _make_client(callbacks=cbs)
        try:
            assert c.callbacks is cbs
        finally:
            await c._callback_handler.close()  # noqa: SLF001

    async def test_init_accepts_protocol_override(self) -> None:
        c = await _make_client(protocol=XMPP)
        try:
            assert c.protocol == XMPP
        finally:
            await c._callback_handler.close()  # noqa: SLF001

    async def test_init_uses_running_loop_when_no_loop_given(self) -> None:
        c = await _make_client()
        try:
            assert c._loop is asyncio.get_running_loop()  # noqa: SLF001
        finally:
            await c._callback_handler.close()  # noqa: SLF001

    async def test_name_falls_back_to_ip_when_no_friendly_name(self, client) -> None:
        assert client.name == "10.0.0.42"

    async def test_name_returns_friendly_name_when_present(self, client) -> None:
        client._hub_config = client._hub_config._replace(  # noqa: SLF001
            discover_info={"friendlyName": "Den"}
        )
        assert client.name == "Den"

    async def test_init_registers_core_handlers_on_response_handler(
        self, client
    ) -> None:
        # 4 core handlers are registered in __init__:
        # START_ACTIVITY_FINISHED, START_ACTIVITY_NOTIFY_STARTED,
        # STOP_ACTIVITY_NOTIFY_STARTED, NOTIFY.
        assert len(client._callback_handler._handler_list) == 4  # noqa: SLF001


class TestCallbacksSetter:
    async def test_setter_updates_callbacks_and_propagates(self, client) -> None:
        fake_conn = MagicMock()
        client._hub_connection = fake_conn  # noqa: SLF001

        new_cbs = _make_callbacks(
            connect=MagicMock(name="cn"), disconnect=MagicMock(name="dc")
        )
        client.callbacks = new_cbs

        assert client.callbacks is new_cbs
        assert fake_conn.callbacks.connect is new_cbs.connect
        assert fake_conn.callbacks.disconnect is new_cbs.disconnect


class TestLookups:
    @pytest_asyncio.fixture
    async def populated_client(self, client) -> HarmonyClient:
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

    async def test_get_activity_id_match(self, populated_client) -> None:
        assert populated_client.get_activity_id("Watch TV") == 1

    async def test_get_activity_id_case_insensitive(self, populated_client) -> None:
        assert populated_client.get_activity_id("WATCH tv") == 1

    async def test_get_activity_id_none_when_unknown(self, populated_client) -> None:
        assert populated_client.get_activity_id("Sleep") is None

    async def test_get_activity_id_none_when_input_none(self, populated_client) -> None:
        assert populated_client.get_activity_id(None) is None

    async def test_get_activity_name_match(self, populated_client) -> None:
        assert populated_client.get_activity_name(2) == "Listen Music"

    async def test_get_activity_name_accepts_string_id(self, populated_client) -> None:
        assert populated_client.get_activity_name("2") == "Listen Music"

    async def test_get_activity_name_none_when_unknown(self, populated_client) -> None:
        assert populated_client.get_activity_name(999) is None

    async def test_get_activity_name_none_when_input_none(
        self, populated_client
    ) -> None:
        assert populated_client.get_activity_name(None) is None

    async def test_get_device_id_match(self, populated_client) -> None:
        assert populated_client.get_device_id("TV") == 100

    async def test_get_device_id_none_when_unknown(self, populated_client) -> None:
        assert populated_client.get_device_id("Toaster") is None

    async def test_get_device_id_none_when_input_none(self, populated_client) -> None:
        assert populated_client.get_device_id(None) is None

    async def test_get_device_name_match(self, populated_client) -> None:
        assert populated_client.get_device_name(200) == "Receiver"

    async def test_get_device_name_accepts_string_id(self, populated_client) -> None:
        assert populated_client.get_device_name("200") == "Receiver"

    async def test_get_device_name_none_when_unknown(self, populated_client) -> None:
        assert populated_client.get_device_name(999) is None

    async def test_get_device_name_none_when_input_none(self, populated_client) -> None:
        assert populated_client.get_device_name(None) is None


class TestHandlerDelegation:
    async def test_register_handler_delegates(self, client) -> None:
        client._callback_handler = MagicMock()  # noqa: SLF001
        client._callback_handler.register_handler.return_value = "uuid-1"  # noqa: SLF001
        result = client.register_handler("a", b=1)
        assert result == "uuid-1"
        client._callback_handler.register_handler.assert_called_once_with("a", b=1)  # noqa: SLF001

    async def test_unregister_handler_delegates(self, client) -> None:
        client._callback_handler = MagicMock()  # noqa: SLF001
        client._callback_handler.unregister_handler.return_value = True  # noqa: SLF001
        result = client.unregister_handler("uuid-1")
        assert result is True
        client._callback_handler.unregister_handler.assert_called_once_with("uuid-1")  # noqa: SLF001


class TestWebsocketOrXmpp:
    async def test_websocket_available_selects_websockets(self, client) -> None:
        with (
            patch(
                "asyncio.open_connection",
                new=AsyncMock(return_value=(MagicMock(), MagicMock())),
            ),
            patch("aioharmony.hubconnector_websocket.HubConnector") as ws_connector,
        ):
            ok = await client._websocket_or_xmpp()  # noqa: SLF001
        assert ok is True
        assert client.protocol == WEBSOCKETS
        ws_connector.assert_called_once()

    async def test_connection_refused_falls_back_to_xmpp(self, client) -> None:
        with (
            patch(
                "asyncio.open_connection",
                new=AsyncMock(side_effect=ConnectionRefusedError),
            ),
            patch("aioharmony.hubconnector_xmpp.HubConnector") as xmpp_connector,
        ):
            ok = await client._websocket_or_xmpp()  # noqa: SLF001
        assert ok is True
        assert client.protocol == XMPP
        xmpp_connector.assert_called_once()

    async def test_oserror_returns_false_when_protocol_unknown(self, client) -> None:
        with patch("asyncio.open_connection", new=AsyncMock(side_effect=OSError)):
            ok = await client._websocket_or_xmpp()  # noqa: SLF001
        assert ok is False
        assert client.protocol is None

    async def test_explicit_xmpp_skips_probe(self, client) -> None:
        client._protocol = XMPP  # noqa: SLF001
        with (
            patch("asyncio.open_connection", new=AsyncMock()) as probe,
            patch("aioharmony.hubconnector_xmpp.HubConnector") as xmpp_connector,
        ):
            ok = await client._websocket_or_xmpp()  # noqa: SLF001
        assert ok is True
        assert client.protocol == XMPP
        probe.assert_not_called()
        xmpp_connector.assert_called_once()


class TestClose:
    async def test_close_with_no_hub_connection_closes_callback_handler(
        self, client
    ) -> None:
        client._hub_connection = None  # noqa: SLF001
        # Replace callback_handler after init so we don't double-close in teardown.
        client._callback_handler = MagicMock()  # noqa: SLF001
        client._callback_handler.close = AsyncMock()  # noqa: SLF001

        await client.close()

        client._callback_handler.close.assert_awaited_once()  # noqa: SLF001

    async def test_close_closes_hub_connection_and_handler(self, client) -> None:
        client._hub_connection = MagicMock()  # noqa: SLF001
        client._hub_connection.close = AsyncMock()  # noqa: SLF001
        client._callback_handler = MagicMock()  # noqa: SLF001
        client._callback_handler.close = AsyncMock()  # noqa: SLF001

        await client.close()

        client._hub_connection.close.assert_awaited_once()  # noqa: SLF001
        client._callback_handler.close.assert_awaited_once()  # noqa: SLF001

    async def test_close_propagates_hub_connection_exception(self, client) -> None:
        client._hub_connection = MagicMock()  # noqa: SLF001
        client._hub_connection.close = AsyncMock(side_effect=RuntimeError("boom"))  # noqa: SLF001
        client._callback_handler = MagicMock()  # noqa: SLF001
        client._callback_handler.close = AsyncMock()  # noqa: SLF001

        with pytest.raises(RuntimeError, match="boom"):
            await client.close()

        client._callback_handler.close.assert_awaited_once()  # noqa: SLF001

    async def test_close_converts_hub_timeout_to_aiotimeout(self, client) -> None:
        client._hub_connection = MagicMock()  # noqa: SLF001
        client._hub_connection.close = AsyncMock(side_effect=asyncio.TimeoutError)  # noqa: SLF001
        client._callback_handler = MagicMock()  # noqa: SLF001
        client._callback_handler.close = AsyncMock()  # noqa: SLF001

        with pytest.raises(aioexc.TimeOut):
            await client.close()

    async def test_close_raises_when_callback_handler_times_out(self, client) -> None:
        client._hub_connection = None  # noqa: SLF001
        client._callback_handler = MagicMock()  # noqa: SLF001
        client._callback_handler.close = AsyncMock(side_effect=asyncio.TimeoutError)  # noqa: SLF001

        with pytest.raises(aioexc.TimeOut):
            await client.close()


class TestDisconnect:
    async def test_disconnect_delegates_to_hub_connection(self, client) -> None:
        client._hub_connection = MagicMock()  # noqa: SLF001
        client._hub_connection.hub_disconnect = AsyncMock()  # noqa: SLF001

        await client.disconnect()

        client._hub_connection.hub_disconnect.assert_awaited_once()  # noqa: SLF001

    async def test_disconnect_converts_timeout_to_aiotimeout(self, client) -> None:
        client._hub_connection = MagicMock()  # noqa: SLF001
        client._hub_connection.hub_disconnect = AsyncMock(  # noqa: SLF001
            side_effect=asyncio.TimeoutError
        )

        with pytest.raises(aioexc.TimeOut):
            await client.disconnect()
