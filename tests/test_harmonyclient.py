"""Tests for HarmonyClient synchronous helpers and lifecycle paths."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from async_timeout import timeout as real_timeout

import aioharmony.exceptions as aioexc
from aioharmony.const import (
    WEBSOCKETS,
    XMPP,
    ClientCallbackType,
    ConnectorCallbackType,
    SendCommandDevice,
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


# ---------------------------------------------------------------------------
# send_to_hub
# ---------------------------------------------------------------------------


async def test_send_to_hub_default_params_dispatches_get_request(
    client: HarmonyClient,
) -> None:
    """Default params populate verb=get/format=json and hub_send is awaited."""
    client._hub_connection = MagicMock()  # noqa: SLF001
    client._hub_connection.hub_send = AsyncMock(return_value=True)  # noqa: SLF001

    result = await client.send_to_hub(command="get_config", wait=False)

    assert result is True
    call_kwargs = client._hub_connection.hub_send.await_args.kwargs  # noqa: SLF001
    assert call_kwargs["params"] == {"verb": "get", "format": "json"}
    assert "config" in call_kwargs["command"]


async def test_send_to_hub_wait_false_returns_true_when_send_not_future(
    client: HarmonyClient,
) -> None:
    client._hub_connection = MagicMock()  # noqa: SLF001
    client._hub_connection.hub_send = AsyncMock(return_value="ok")  # noqa: SLF001

    result = await client.send_to_hub(command="get_config", wait=False)

    assert result is True


async def test_send_to_hub_returns_false_and_unregisters_when_send_returns_none(
    client: HarmonyClient,
) -> None:
    """send_response is None → returns False and any registered handler is dropped."""
    client._hub_connection = MagicMock()  # noqa: SLF001
    client._hub_connection.hub_send = AsyncMock(return_value=None)  # noqa: SLF001

    result = await client.send_to_hub(command="get_config")

    assert result is False
    # The wait=True path registered a handler that should now be gone.
    assert client._callback_handler._handler_list  # noqa: SLF001
    # Only the 4 core handlers from __init__ remain (no orphan send handler).
    assert len(client._callback_handler._handler_list) == 4  # noqa: SLF001


async def test_send_to_hub_uses_send_future_when_returned(
    client: HarmonyClient,
) -> None:
    """If hub_send returns a future, that future's result becomes the response."""
    fut = asyncio.get_running_loop().create_future()
    fut.set_result({"data": {"foo": "bar"}})
    client._hub_connection = MagicMock()  # noqa: SLF001
    client._hub_connection.hub_send = AsyncMock(return_value=fut)  # noqa: SLF001

    result = await client.send_to_hub(command="get_config")

    assert result == {"data": {"foo": "bar"}}


async def test_send_to_hub_timeout_on_hub_send_raises_timeout(
    client: HarmonyClient,
) -> None:
    client._hub_connection = MagicMock()  # noqa: SLF001
    client._hub_connection.hub_send = AsyncMock(  # noqa: SLF001
        side_effect=asyncio.TimeoutError
    )

    with pytest.raises(aioexc.TimeOut):
        await client.send_to_hub(command="get_config")

    # Send handler was cleaned up.
    assert len(client._callback_handler._handler_list) == 4  # noqa: SLF001


async def test_send_to_hub_post_flag_propagates(client: HarmonyClient) -> None:
    client._hub_connection = MagicMock()  # noqa: SLF001
    client._hub_connection.hub_send = AsyncMock(return_value=True)  # noqa: SLF001

    await client.send_to_hub(command="provision_info", post=True, wait=False)

    assert client._hub_connection.hub_send.await_args.kwargs["post"] is True  # noqa: SLF001


# ---------------------------------------------------------------------------
# _get_config
# ---------------------------------------------------------------------------


def _config_response_ok() -> dict:
    return {
        "code": 200,
        "data": {
            "activity": [{"id": "1", "label": "Watch TV"}],
            "device": [{"id": "100", "label": "TV"}],
        },
    }


async def test_get_config_success_populates_activities_and_devices(
    client: HarmonyClient,
) -> None:
    with patch.object(
        client, "send_to_hub", AsyncMock(return_value=_config_response_ok())
    ):
        result = await client._get_config()  # noqa: SLF001

    assert result == _config_response_ok()["data"]
    assert client.hub_config.activities == [
        {"id": 1, "name": "Watch TV", "name_lowercase": "watch tv"}
    ]
    assert client.hub_config.devices == [
        {"id": 100, "name": "TV", "name_lowercase": "tv"}
    ]


async def test_get_config_returns_none_when_response_empty(
    client: HarmonyClient,
) -> None:
    with patch.object(client, "send_to_hub", AsyncMock(return_value=None)):
        result = await client._get_config()  # noqa: SLF001

    assert result is None


async def test_get_config_returns_none_when_code_not_200(
    client: HarmonyClient,
) -> None:
    with patch.object(
        client, "send_to_hub", AsyncMock(return_value={"code": 500, "data": {}})
    ):
        result = await client._get_config()  # noqa: SLF001

    assert result is None


async def test_get_config_retries_once_on_timeout(client: HarmonyClient) -> None:
    send = AsyncMock(side_effect=[aioexc.TimeOut, _config_response_ok()])
    with patch.object(client, "send_to_hub", send):
        result = await client._get_config()  # noqa: SLF001

    assert result == _config_response_ok()["data"]
    assert send.await_count == 2


async def test_get_config_raises_timeout_after_second_failure(
    client: HarmonyClient,
) -> None:
    send = AsyncMock(side_effect=[aioexc.TimeOut, aioexc.TimeOut])
    with patch.object(client, "send_to_hub", send), pytest.raises(aioexc.TimeOut):
        await client._get_config()  # noqa: SLF001


# ---------------------------------------------------------------------------
# _retrieve_provision_info / _retrieve_discovery_info / _retrieve_hub_info
# ---------------------------------------------------------------------------


async def test_retrieve_provision_info_success_updates_info(
    client: HarmonyClient,
) -> None:
    response = {"code": 200, "data": {"activeRemoteId": "abc"}}
    with patch.object(client, "send_to_hub", AsyncMock(return_value=response)):
        result = await client._retrieve_provision_info()  # noqa: SLF001

    assert result == {"activeRemoteId": "abc"}
    assert client.hub_config.info == {"activeRemoteId": "abc"}


async def test_retrieve_provision_info_accepts_string_code_200(
    client: HarmonyClient,
) -> None:
    response = {"code": "200", "data": {"activeRemoteId": "abc"}}
    with patch.object(client, "send_to_hub", AsyncMock(return_value=response)):
        result = await client._retrieve_provision_info()  # noqa: SLF001

    assert result == {"activeRemoteId": "abc"}


async def test_retrieve_provision_info_non_200_does_not_update(
    client: HarmonyClient,
) -> None:
    with patch.object(
        client, "send_to_hub", AsyncMock(return_value={"code": 500, "data": {"x": 1}})
    ):
        result = await client._retrieve_provision_info()  # noqa: SLF001

    assert result is None
    assert client.hub_config.info == {}


async def test_retrieve_provision_info_both_timeouts_returns_none(
    client: HarmonyClient,
) -> None:
    send = AsyncMock(side_effect=[aioexc.TimeOut, aioexc.TimeOut])
    with patch.object(client, "send_to_hub", send):
        result = await client._retrieve_provision_info()  # noqa: SLF001

    assert result is None
    assert send.await_count == 2


async def test_retrieve_provision_info_retries_after_first_timeout(
    client: HarmonyClient,
) -> None:
    response = {"code": 200, "data": {"activeRemoteId": "abc"}}
    send = AsyncMock(side_effect=[aioexc.TimeOut, response])
    with patch.object(client, "send_to_hub", send):
        result = await client._retrieve_provision_info()  # noqa: SLF001

    assert result == {"activeRemoteId": "abc"}
    assert send.await_count == 2


async def test_retrieve_discovery_info_success_updates_discover_info(
    client: HarmonyClient,
) -> None:
    response = {"code": 200, "data": {"friendlyName": "Den"}}
    with patch.object(client, "send_to_hub", AsyncMock(return_value=response)):
        await client._retrieve_discovery_info()  # noqa: SLF001

    assert client.hub_config.discover_info == {"friendlyName": "Den"}


async def test_retrieve_discovery_info_non_200_does_not_update(
    client: HarmonyClient,
) -> None:
    with patch.object(
        client, "send_to_hub", AsyncMock(return_value={"code": 500, "data": {}})
    ):
        await client._retrieve_discovery_info()  # noqa: SLF001

    assert client.hub_config.discover_info == {}


async def test_retrieve_discovery_info_both_timeouts_silently_returns(
    client: HarmonyClient,
) -> None:
    send = AsyncMock(side_effect=[aioexc.TimeOut, aioexc.TimeOut])
    with patch.object(client, "send_to_hub", send):
        await client._retrieve_discovery_info()  # noqa: SLF001

    assert client.hub_config.discover_info == {}
    assert send.await_count == 2


async def test_retrieve_hub_info_returns_provision_result(
    client: HarmonyClient,
) -> None:
    with (
        patch.object(
            client,
            "_retrieve_provision_info",
            AsyncMock(return_value={"activeRemoteId": "abc"}),
        ),
        patch.object(client, "_retrieve_discovery_info", AsyncMock(return_value=None)),
    ):
        result = await client._retrieve_hub_info()  # noqa: SLF001

    assert result == {"activeRemoteId": "abc"}


async def test_retrieve_hub_info_reraises_exception_from_children(
    client: HarmonyClient,
) -> None:
    class _BoomError(RuntimeError):
        pass

    with (
        patch.object(
            client, "_retrieve_provision_info", AsyncMock(side_effect=_BoomError())
        ),
        patch.object(client, "_retrieve_discovery_info", AsyncMock(return_value=None)),
        pytest.raises(_BoomError),
    ):
        await client._retrieve_hub_info()  # noqa: SLF001


# ---------------------------------------------------------------------------
# _get_current_activity
# ---------------------------------------------------------------------------


async def test_get_current_activity_success_sets_id_and_fires_callback(
    populated_client: HarmonyClient,
) -> None:
    cb = MagicMock()
    populated_client._callbacks = populated_client._callbacks._replace(  # noqa: SLF001
        new_activity=cb
    )
    response = {"code": 200, "data": {"result": "1"}}
    with (
        patch.object(populated_client, "send_to_hub", AsyncMock(return_value=response)),
        patch("aioharmony.harmonyclient.call_callback") as mock_call,
    ):
        ok = await populated_client._get_current_activity()  # noqa: SLF001

    assert ok is True
    assert populated_client.current_activity_id == 1
    mock_call.assert_called_once()
    assert mock_call.call_args.kwargs["callback_handler"] is cb


async def test_get_current_activity_no_callback_when_none(
    populated_client: HarmonyClient,
) -> None:
    response = {"code": 200, "data": {"result": "1"}}
    with (
        patch.object(populated_client, "send_to_hub", AsyncMock(return_value=response)),
        patch("aioharmony.harmonyclient.call_callback") as mock_call,
    ):
        ok = await populated_client._get_current_activity()  # noqa: SLF001

    assert ok is True
    assert populated_client.current_activity_id == 1
    mock_call.assert_not_called()


async def test_get_current_activity_returns_false_when_response_empty(
    client: HarmonyClient,
) -> None:
    with patch.object(client, "send_to_hub", AsyncMock(return_value=None)):
        ok = await client._get_current_activity()  # noqa: SLF001
    assert ok is False


async def test_get_current_activity_returns_false_when_code_not_200(
    client: HarmonyClient,
) -> None:
    with patch.object(
        client,
        "send_to_hub",
        AsyncMock(return_value={"code": 500, "data": {"result": "1"}}),
    ):
        ok = await client._get_current_activity()  # noqa: SLF001
    assert ok is False


async def test_get_current_activity_both_timeouts_returns_false(
    client: HarmonyClient,
) -> None:
    send = AsyncMock(side_effect=[aioexc.TimeOut, aioexc.TimeOut])
    with patch.object(client, "send_to_hub", send):
        ok = await client._get_current_activity()  # noqa: SLF001
    assert ok is False
    assert send.await_count == 2


# ---------------------------------------------------------------------------
# _notification_callback
# ---------------------------------------------------------------------------


async def test_notification_callback_noop_when_data_missing(
    client: HarmonyClient,
) -> None:
    with patch.object(client, "refresh_info_from_hub", AsyncMock()) as refresh:
        await client._notification_callback({})  # noqa: SLF001
    refresh.assert_not_awaited()


async def test_notification_callback_noop_when_sync_in_progress(
    client: HarmonyClient,
) -> None:
    message = {"data": {"configVersion": 99, "syncStatus": 1}}
    with patch.object(client, "refresh_info_from_hub", AsyncMock()) as refresh:
        await client._notification_callback(message)  # noqa: SLF001
    refresh.assert_not_awaited()


async def test_notification_callback_noop_when_version_unchanged(
    client: HarmonyClient,
) -> None:
    client._hub_config = client._hub_config._replace(config_version=7)  # noqa: SLF001
    message = {"data": {"configVersion": 7, "syncStatus": 2}}
    with patch.object(client, "refresh_info_from_hub", AsyncMock()) as refresh:
        await client._notification_callback(message)  # noqa: SLF001
    refresh.assert_not_awaited()


async def test_notification_callback_refreshes_on_version_change(
    client: HarmonyClient,
) -> None:
    client._hub_config = client._hub_config._replace(config_version=7)  # noqa: SLF001
    message = {"data": {"configVersion": 8, "syncStatus": 2}}
    with patch.object(client, "refresh_info_from_hub", AsyncMock()) as refresh:
        await client._notification_callback(message)  # noqa: SLF001
    refresh.assert_awaited_once()
    assert client.hub_config.config_version == 8


# ---------------------------------------------------------------------------
# _update_activity_callback
# ---------------------------------------------------------------------------


async def test_update_activity_callback_falls_back_to_get_current(
    client: HarmonyClient,
) -> None:
    """A message with no activityId triggers a fresh fetch."""
    with patch.object(
        client, "_get_current_activity", AsyncMock(return_value=True)
    ) as gca:
        await client._update_activity_callback({"data": None})  # noqa: SLF001
    gca.assert_awaited_once()


async def test_update_activity_callback_sets_id_and_fires_callback(
    populated_client: HarmonyClient,
) -> None:
    cb = MagicMock()
    populated_client._callbacks = populated_client._callbacks._replace(  # noqa: SLF001
        new_activity=cb
    )
    with patch("aioharmony.harmonyclient.call_callback") as mock_call:
        await populated_client._update_activity_callback(  # noqa: SLF001
            {"data": {"activityId": "2"}}
        )

    assert populated_client.current_activity_id == 2
    mock_call.assert_called_once()
    assert mock_call.call_args.kwargs["callback_handler"] is cb


# ---------------------------------------------------------------------------
# _update_start_activity_callback
# ---------------------------------------------------------------------------


async def test_update_start_activity_callback_power_off_to_power_off_is_noop(
    client: HarmonyClient,
) -> None:
    client._current_activity_id = -1  # noqa: SLF001
    cb = MagicMock()
    client._callbacks = client._callbacks._replace(new_activity_starting=cb)  # noqa: SLF001
    with patch("aioharmony.harmonyclient.call_callback") as mock_call:
        await client._update_start_activity_callback(  # noqa: SLF001
            {"data": {"activityStatus": 0, "activityId": "-1"}}
        )

    assert client.current_activity_id == -1
    mock_call.assert_not_called()


async def test_update_start_activity_callback_power_off_from_active(
    populated_client: HarmonyClient,
) -> None:
    populated_client._current_activity_id = 1  # noqa: SLF001
    cb = MagicMock()
    populated_client._callbacks = populated_client._callbacks._replace(  # noqa: SLF001
        new_activity_starting=cb
    )
    with patch("aioharmony.harmonyclient.call_callback") as mock_call:
        await populated_client._update_start_activity_callback(  # noqa: SLF001
            {"data": {"activityStatus": 0, "activityId": "-1"}}
        )

    assert populated_client.current_activity_id == -1
    mock_call.assert_called_once()


async def test_update_start_activity_callback_starting_activity(
    populated_client: HarmonyClient,
) -> None:
    cb = MagicMock()
    populated_client._callbacks = populated_client._callbacks._replace(  # noqa: SLF001
        new_activity_starting=cb
    )
    with patch("aioharmony.harmonyclient.call_callback") as mock_call:
        await populated_client._update_start_activity_callback(  # noqa: SLF001
            {"data": {"activityStatus": 2, "activityId": "1"}}
        )

    assert populated_client.current_activity_id == 1
    mock_call.assert_called_once()


async def test_update_start_activity_callback_no_data_clears_id(
    populated_client: HarmonyClient,
) -> None:
    populated_client._current_activity_id = 1  # noqa: SLF001
    with patch("aioharmony.harmonyclient.call_callback"):
        await populated_client._update_start_activity_callback({"data": None})  # noqa: SLF001

    assert populated_client.current_activity_id is None


# ---------------------------------------------------------------------------
# refresh_info_from_hub
# ---------------------------------------------------------------------------


async def test_refresh_info_from_hub_happy_path_fires_callback(
    client: HarmonyClient,
) -> None:
    cb = MagicMock()
    client._callbacks = client._callbacks._replace(config_updated=cb)  # noqa: SLF001
    with (
        patch.object(client, "_get_config", AsyncMock(return_value={"x": 1})),
        patch.object(client, "_retrieve_hub_info", AsyncMock(return_value={})),
        patch.object(client, "_get_current_activity", AsyncMock(return_value=True)),
        patch("aioharmony.harmonyclient.call_callback") as mock_call,
    ):
        await client.refresh_info_from_hub()

    mock_call.assert_called_once()
    assert mock_call.call_args.kwargs["callback_handler"] is cb


async def test_refresh_info_from_hub_no_callback_when_unset(
    client: HarmonyClient,
) -> None:
    with (
        patch.object(client, "_get_config", AsyncMock(return_value={})),
        patch.object(client, "_retrieve_hub_info", AsyncMock(return_value={})),
        patch.object(client, "_get_current_activity", AsyncMock(return_value=True)),
        patch("aioharmony.harmonyclient.call_callback") as mock_call,
    ):
        await client.refresh_info_from_hub()

    mock_call.assert_not_called()


async def test_refresh_info_from_hub_timeout_result_short_circuits(
    client: HarmonyClient,
) -> None:
    """A TimeOut from _get_config bails before _get_current_activity is called."""
    with (
        patch.object(client, "_get_config", AsyncMock(side_effect=aioexc.TimeOut)),
        patch.object(client, "_retrieve_hub_info", AsyncMock(return_value={})),
        patch.object(client, "_get_current_activity", AsyncMock()) as gca,
    ):
        await client.refresh_info_from_hub()

    gca.assert_not_awaited()


async def test_refresh_info_from_hub_other_exception_raises(
    client: HarmonyClient,
) -> None:
    class _BoomError(RuntimeError):
        pass

    with (
        patch.object(client, "_get_config", AsyncMock(side_effect=_BoomError())),
        patch.object(client, "_retrieve_hub_info", AsyncMock(return_value={})),
        pytest.raises(_BoomError),
    ):
        await client.refresh_info_from_hub()


# ---------------------------------------------------------------------------
# connect (orchestrator)
# ---------------------------------------------------------------------------


async def test_connect_returns_false_when_transport_probe_fails(
    client: HarmonyClient,
) -> None:
    with patch.object(client, "_websocket_or_xmpp", AsyncMock(return_value=False)):
        result = await client.connect()
    assert result is False


async def test_connect_returns_false_when_hub_connect_returns_false(
    client: HarmonyClient,
) -> None:
    client._hub_connection = MagicMock()  # noqa: SLF001
    client._hub_connection.hub_connect = AsyncMock(return_value=False)  # noqa: SLF001
    result = await client.connect()
    assert result is False


async def test_connect_converts_hub_connect_timeout_to_aiotimeout(
    client: HarmonyClient,
) -> None:
    client._hub_connection = MagicMock()  # noqa: SLF001
    client._hub_connection.hub_connect = AsyncMock(  # noqa: SLF001
        side_effect=asyncio.TimeoutError
    )
    with pytest.raises(aioexc.TimeOut):
        await client.connect()


async def test_connect_populates_hub_state_and_fires_connect_callback(
    client: HarmonyClient,
) -> None:
    cb = MagicMock()
    client._callbacks = client._callbacks._replace(connect=cb)  # noqa: SLF001
    client._hub_connection = MagicMock()  # noqa: SLF001
    client._hub_connection.hub_connect = AsyncMock(return_value=True)  # noqa: SLF001
    client._hub_connection.callbacks = ConnectorCallbackType(None, None)  # noqa: SLF001

    state_response = {"data": {"configVersion": 42, "extra": "x"}}
    with (
        patch.object(client, "send_to_hub", AsyncMock(return_value=state_response)),
        patch.object(client, "refresh_info_from_hub", AsyncMock()),
        patch("aioharmony.harmonyclient.call_callback") as mock_call,
    ):
        result = await client.connect()

    assert result is True
    assert client.hub_config.config_version == 42
    assert client.hub_config.hub_state == state_response["data"]
    mock_call.assert_called_once()
    assert mock_call.call_args.kwargs["callback_handler"] is cb
    # Connector callbacks were refreshed with the user-provided pair.
    assert client._hub_connection.callbacks.connect is cb  # noqa: SLF001


async def test_connect_handles_get_current_state_timeout(
    client: HarmonyClient,
) -> None:
    """A TimeOut from get_current_state is logged but doesn't fail the connect."""
    client._hub_connection = MagicMock()  # noqa: SLF001
    client._hub_connection.hub_connect = AsyncMock(return_value=True)  # noqa: SLF001
    client._hub_connection.callbacks = ConnectorCallbackType(None, None)  # noqa: SLF001

    with (
        patch.object(client, "send_to_hub", AsyncMock(side_effect=aioexc.TimeOut)),
        patch.object(client, "refresh_info_from_hub", AsyncMock()),
    ):
        result = await client.connect()

    assert result is True
    # config_version was NOT updated since the response never arrived.
    assert client.hub_config.config_version is None


async def test_connect_reraises_unexpected_exception_from_send(
    client: HarmonyClient,
) -> None:
    class _BoomError(RuntimeError):
        pass

    client._hub_connection = MagicMock()  # noqa: SLF001
    client._hub_connection.hub_connect = AsyncMock(return_value=True)  # noqa: SLF001
    client._hub_connection.callbacks = ConnectorCallbackType(None, None)  # noqa: SLF001

    with (
        patch.object(client, "send_to_hub", AsyncMock(side_effect=_BoomError())),
        patch.object(client, "refresh_info_from_hub", AsyncMock()),
        pytest.raises(_BoomError),
    ):
        await client.connect()


# ---------------------------------------------------------------------------
# start_activity
# ---------------------------------------------------------------------------


def _capture_activity_handlers(client: HarmonyClient) -> list:
    """Patch register/unregister, returning the callback closures in
    registration order: started, in_progress, helpdiscretes, completed.
    """
    captured: list = []

    def fake_register(handler: Any, msgid: str) -> str:
        captured.append(handler.handler_obj)
        return f"uuid-{len(captured)}"

    client.register_handler = MagicMock(side_effect=fake_register)
    client.unregister_handler = MagicMock(return_value=True)
    return captured


async def test_start_activity_succeeds_on_completion_code_200(
    populated_client: HarmonyClient,
) -> None:
    """A completion message with code 200 resolves to (True, msg)."""
    client = populated_client
    handlers = _capture_activity_handlers(client)

    async def fake_send(**_: Any) -> bool:
        client._loop.call_soon(handlers[3], {"code": 200, "msg": "started"})  # noqa: SLF001
        return True

    with patch.object(client, "send_to_hub", fake_send):
        result = await client.start_activity(1)

    assert result == (True, "started")
    client.unregister_handler.assert_called()


async def test_start_activity_fails_when_run_activity_returns_error_code(
    populated_client: HarmonyClient,
) -> None:
    """A RunActivity code outside {100, 200} resolves to (False, msg)."""
    client = populated_client
    handlers = _capture_activity_handlers(client)

    async def fake_send(**_: Any) -> bool:
        client._loop.call_soon(handlers[0], {"code": 500, "msg": "boom"})  # noqa: SLF001
        return True

    with patch.object(client, "send_to_hub", fake_send):
        result = await client.start_activity(1)

    assert result == (False, "boom")


async def test_start_activity_fails_on_completion_error_code(
    populated_client: HarmonyClient,
) -> None:
    """A completion message with a non-100/200 code resolves to (False, msg)."""
    client = populated_client
    handlers = _capture_activity_handlers(client)

    async def fake_send(**_: Any) -> bool:
        client._loop.call_soon(handlers[3], {"code": 500, "msg": "nope"})  # noqa: SLF001
        return True

    with patch.object(client, "send_to_hub", fake_send):
        result = await client.start_activity(1)

    assert result == (False, "nope")


async def test_start_activity_ignores_progress_and_in_progress_completion(
    populated_client: HarmonyClient,
) -> None:
    """Progress messages and a code-100 completion don't set a result; the
    final code-200 completion does.
    """
    client = populated_client
    handlers = _capture_activity_handlers(client)

    async def fake_send(**_: Any) -> bool:
        client._loop.call_soon(handlers[1], {"data": {"done": 1, "total": 3}})  # noqa: SLF001
        client._loop.call_soon(handlers[2], {"data": None})  # noqa: SLF001
        client._loop.call_soon(handlers[3], {"code": 100})  # noqa: SLF001
        client._loop.call_soon(handlers[3], {"code": 200, "msg": "done"})  # noqa: SLF001
        return True

    with patch.object(client, "send_to_hub", fake_send):
        result = await client.start_activity(1)

    assert result == (True, "done")


async def test_start_activity_keeps_first_result_when_set_twice(
    populated_client: HarmonyClient,
) -> None:
    """Once a result is set, a later message can't overwrite it."""
    client = populated_client
    handlers = _capture_activity_handlers(client)

    async def fake_send(**_: Any) -> bool:
        client._loop.call_soon(handlers[3], {"code": 200, "msg": "first"})  # noqa: SLF001
        client._loop.call_soon(handlers[3], {"code": 500, "msg": "second"})  # noqa: SLF001
        return True

    with patch.object(client, "send_to_hub", fake_send):
        result = await client.start_activity(1)

    assert result == (True, "first")


async def test_start_activity_raises_timeout_when_never_completed(
    populated_client: HarmonyClient,
) -> None:
    """No completion message within the deadline raises TimeOut."""
    client = populated_client
    _capture_activity_handlers(client)

    with (
        patch("aioharmony.harmonyclient.timeout", lambda _t: real_timeout(0)),
        patch.object(client, "send_to_hub", AsyncMock(return_value=True)),
        pytest.raises(aioexc.TimeOut),
    ):
        await client.start_activity(1)

    client.unregister_handler.assert_called()


# ---------------------------------------------------------------------------
# send_commands
# ---------------------------------------------------------------------------


async def test_send_commands_returns_empty_when_all_succeed(
    populated_client: HarmonyClient,
) -> None:
    """A 200 response is treated as success and produces no error entries; a
    bare sleep value in the list is honoured without a future.
    """
    client = populated_client
    cmd = SendCommandDevice(device=100, command="PowerOn", delay=0)

    def fake_send_command(command: Any, callback_handler: Any) -> tuple[str, str]:
        callback_handler.handler_obj.set_result(
            {"id": "press-1", "code": 200, "msg": "ok"}
        )
        return "press-1", "release-1"

    with patch.object(
        client, "_send_command", AsyncMock(side_effect=fake_send_command)
    ):
        result = await client.send_commands([0, cmd])

    assert result == []


async def test_send_commands_collects_error_response(
    populated_client: HarmonyClient,
) -> None:
    """A non-200 response is surfaced as a SendCommandResponse."""
    client = populated_client
    cmd = SendCommandDevice(device=100, command="PowerOn", delay=0)

    def fake_send_command(command: Any, callback_handler: Any) -> tuple[str, str]:
        callback_handler.handler_obj.set_result(
            {"id": "press-1", "code": 500, "msg": "bad"}
        )
        return "press-1", "release-1"

    with patch.object(
        client, "_send_command", AsyncMock(side_effect=fake_send_command)
    ):
        result = await client.send_commands([cmd])

    assert len(result) == 1
    assert result[0].command == cmd
    assert result[0].code == 500
    assert result[0].msg == "bad"


async def test_send_commands_skips_response_without_message_id(
    populated_client: HarmonyClient,
) -> None:
    """A response missing an id is logged and skipped, not raised."""
    client = populated_client
    cmd = SendCommandDevice(device=100, command="PowerOn", delay=0)

    def fake_send_command(command: Any, callback_handler: Any) -> tuple[str, str]:
        callback_handler.handler_obj.set_result({"code": 500, "msg": "x"})
        return "press-1", "release-1"

    with patch.object(
        client, "_send_command", AsyncMock(side_effect=fake_send_command)
    ):
        result = await client.send_commands([cmd])

    assert result == []


async def test_send_commands_skips_unknown_message_id(
    populated_client: HarmonyClient,
) -> None:
    """A response whose id isn't in the sent map is skipped."""
    client = populated_client
    cmd = SendCommandDevice(device=100, command="PowerOn", delay=0)

    def fake_send_command(command: Any, callback_handler: Any) -> tuple[None, None]:
        callback_handler.handler_obj.set_result(
            {"id": "unknown", "code": 500, "msg": "x"}
        )
        return None, None

    with patch.object(
        client, "_send_command", AsyncMock(side_effect=fake_send_command)
    ):
        result = await client.send_commands([cmd])

    assert result == []


# ---------------------------------------------------------------------------
# _send_command
# ---------------------------------------------------------------------------


async def test_send_command_press_and_release_with_zero_delay(
    populated_client: HarmonyClient,
) -> None:
    """A zero-delay command sends press then release and returns both ids."""
    client = populated_client
    client.register_handler = MagicMock(return_value="uuid")
    cmd = SendCommandDevice(device=100, command="PowerOn", delay=0)

    with patch.object(client, "send_to_hub", AsyncMock(return_value=True)) as send:
        press, release = await client._send_command(cmd, MagicMock())  # noqa: SLF001

    assert press is not None
    assert release is not None
    assert press != release
    assert send.await_count == 2
    assert client.register_handler.call_count == 2


async def test_send_command_sleeps_between_press_and_release_when_delayed(
    populated_client: HarmonyClient,
) -> None:
    """A positive delay sleeps for that interval between press and release."""
    client = populated_client
    client.register_handler = MagicMock(return_value="uuid")
    cmd = SendCommandDevice(device=100, command="PowerOn", delay=0.5)

    with (
        patch("asyncio.sleep", AsyncMock()) as sleep,
        patch.object(client, "send_to_hub", AsyncMock(return_value=True)),
    ):
        await client._send_command(cmd, MagicMock())  # noqa: SLF001

    sleep.assert_awaited_once_with(0.5)


async def test_send_command_aborts_when_press_send_fails(
    populated_client: HarmonyClient,
) -> None:
    """A falsy response to the press send returns (None, None) without release."""
    client = populated_client
    client.register_handler = MagicMock(return_value="uuid")
    cmd = SendCommandDevice(device=100, command="PowerOn", delay=0)

    with patch.object(client, "send_to_hub", AsyncMock(return_value=None)) as send:
        result = await client._send_command(cmd, MagicMock())  # noqa: SLF001

    assert result == (None, None)
    assert send.await_count == 1


# ---------------------------------------------------------------------------
# send_commands / start_activity / _send_command edge cases
# ---------------------------------------------------------------------------


async def test_start_activity_returns_failure_when_send_returns_falsy(
    client: HarmonyClient,
) -> None:
    """start_activity aborts immediately instead of hanging when the hub send fails."""
    with patch.object(client, "send_to_hub", AsyncMock(return_value=False)):
        result = await asyncio.wait_for(client.start_activity(1), timeout=1)
    assert result == (False, None)


async def test_send_commands_returns_empty_when_only_sleeps(
    client: HarmonyClient,
) -> None:
    """A command list of only delays creates no futures; wait([]) would raise."""
    result = await client.send_commands([0.0])
    assert result == []


async def test_send_command_handles_none_delay(client: HarmonyClient) -> None:
    """delay=None must not raise a TypeError on the `delay > 0` comparison."""
    cmd = SendCommandDevice(device=100, command="PowerOn", delay=None)
    handler = MagicMock()
    with patch.object(client, "send_to_hub", AsyncMock(return_value=True)):
        msgid_press, msgid_release = await client._send_command(cmd, handler)  # noqa: SLF001
    assert msgid_press is not None
    assert msgid_release is not None
