"""Tests for the websocket listener reconnect paths."""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from aioharmony.const import ConnectorCallbackType
from aioharmony.hubconnector_websocket import HubConnector


class FakeWebSocket:
    """Minimal websocket stub for driving HubConnector._listener.

    `messages` is a deque whose entries are either:
      - an aiohttp.WSMessage-like MagicMock for receive() to return, or
      - an Exception class/instance for receive() to raise.

    Once exhausted, receive() returns a CLOSED message so the loop terminates
    deterministically if the test forgot to set the websocket as closed.
    """

    def __init__(self, messages: list[Any]) -> None:
        self._messages: deque[Any] = deque(messages)
        self.closed = False

    async def receive(self) -> Any:
        if not self._messages:
            self.closed = True
            return _make_message(aiohttp.WSMsgType.CLOSED, data=1000)
        item = self._messages.popleft()
        if isinstance(item, BaseException) or (
            isinstance(item, type) and issubclass(item, BaseException)
        ):
            self.closed = True
            raise item if isinstance(item, BaseException) else item("boom")
        return item

    async def close(self) -> None:
        self.closed = True


def _make_message(msg_type: aiohttp.WSMsgType, data: Any = None) -> MagicMock:
    msg = MagicMock()
    msg.type = msg_type
    msg.data = data
    return msg


def _make_connector() -> HubConnector:
    queue: asyncio.Queue = asyncio.Queue()
    connector = HubConnector(
        ip_address="10.0.0.1",
        response_queue=queue,
        callbacks=ConnectorCallbackType(connect=None, disconnect=None),
    )
    connector._connected = True  # noqa: SLF001
    connector._remote_id = "abc"  # noqa: SLF001
    return connector


async def _run_listener_once(
    connector: HubConnector, fake_ws: FakeWebSocket
) -> AsyncMock:
    """Run _listener and capture a single reconnect attempt.

    Patches hub_connect to a synchronous AsyncMock returning True so that
    _reconnect's retry loop exits after one call. Returns the mock so callers
    can assert on call counts.
    """
    hub_connect = AsyncMock(return_value=True)
    connector.hub_connect = hub_connect  # type: ignore[method-assign]
    # _reconnect closes the session if it is non-None; bypass that work.
    connector.async_close_session = AsyncMock()  # type: ignore[method-assign]

    connector._websocket = fake_ws  # type: ignore[assignment]  # noqa: SLF001
    await connector._listener(fake_ws)  # noqa: SLF001
    return hub_connect


@pytest.mark.asyncio
async def test_listener_reconnects_on_client_error_during_receive() -> None:
    """A ClientError from receive() must trigger reconnect.

    Regression: previously this path broke out of the loop without setting
    have_connection=False, so _reconnect was never called and the integration
    stayed offline.
    """
    fake_ws = FakeWebSocket([aiohttp.ClientError])
    connector = _make_connector()

    hub_connect = await _run_listener_once(connector, fake_ws)

    assert hub_connect.await_count == 1


@pytest.mark.asyncio
async def test_listener_reconnects_on_ws_error_message() -> None:
    """A WSMsgType.ERROR message must trigger reconnect, not spin."""
    fake_ws = FakeWebSocket(
        [_make_message(aiohttp.WSMsgType.ERROR, data=RuntimeError("bad"))]
    )
    connector = _make_connector()

    hub_connect = await _run_listener_once(connector, fake_ws)

    assert hub_connect.await_count == 1


@pytest.mark.asyncio
async def test_listener_reconnects_on_ws_close_message() -> None:
    """A WSMsgType.CLOSE handshake must trigger reconnect immediately."""
    fake_ws = FakeWebSocket([_make_message(aiohttp.WSMsgType.CLOSE, data=1000)])
    connector = _make_connector()

    hub_connect = await _run_listener_once(connector, fake_ws)

    assert hub_connect.await_count == 1


@pytest.mark.asyncio
async def test_listener_reconnects_on_ws_closing_message() -> None:
    """A WSMsgType.CLOSING handshake must trigger reconnect immediately."""
    fake_ws = FakeWebSocket([_make_message(aiohttp.WSMsgType.CLOSING, data=1000)])
    connector = _make_connector()

    hub_connect = await _run_listener_once(connector, fake_ws)

    assert hub_connect.await_count == 1


@pytest.mark.asyncio
async def test_listener_reconnects_on_ws_closed_message() -> None:
    """A WSMsgType.CLOSED message must trigger reconnect (existing behavior)."""
    fake_ws = FakeWebSocket([_make_message(aiohttp.WSMsgType.CLOSED, data=1000)])
    connector = _make_connector()

    hub_connect = await _run_listener_once(connector, fake_ws)

    assert hub_connect.await_count == 1


@pytest.mark.asyncio
async def test_listener_reconnects_on_unexpected_exception() -> None:
    """An unexpected exception inside the loop must trigger reconnect.

    Regression: previously the broad `except Exception` only logged, so the
    listener could spin forever on a recurring error.
    """

    class BoomMessage:
        """A message-like object whose attribute access raises."""

        @property
        def type(self) -> aiohttp.WSMsgType:
            raise RuntimeError("boom")

        @property
        def data(self) -> Any:
            return None

    fake_ws = FakeWebSocket([BoomMessage()])
    connector = _make_connector()

    hub_connect = await _run_listener_once(connector, fake_ws)

    assert hub_connect.await_count == 1


@pytest.mark.asyncio
async def test_listener_does_not_reconnect_when_disconnected() -> None:
    """If the user called disconnect, reconnect must not fire."""
    fake_ws = FakeWebSocket([aiohttp.ClientError])
    connector = _make_connector()
    connector._connected = False  # noqa: SLF001  # simulate explicit disconnect

    hub_connect = await _run_listener_once(connector, fake_ws)

    assert hub_connect.await_count == 0


@pytest.mark.asyncio
async def test_listener_passes_text_message_to_queue() -> None:
    """Sanity check: TEXT messages still flow to the response queue."""
    text_msg = _make_message(aiohttp.WSMsgType.TEXT)
    text_msg.json.return_value = {"hello": "world"}
    fake_ws = FakeWebSocket(
        [text_msg, _make_message(aiohttp.WSMsgType.CLOSED, data=1000)]
    )
    connector = _make_connector()

    await _run_listener_once(connector, fake_ws)

    assert connector._response_queue.get_nowait() == {"hello": "world"}  # noqa: SLF001


@pytest.mark.asyncio
async def test_listener_does_not_reconnect_when_auto_reconnect_disabled() -> None:
    """auto_reconnect=False must suppress reconnect even on ClientError."""
    queue: asyncio.Queue = asyncio.Queue()
    connector = HubConnector(
        ip_address="10.0.0.1",
        response_queue=queue,
        callbacks=ConnectorCallbackType(connect=None, disconnect=None),
        auto_reconnect=False,
    )
    connector._connected = True  # noqa: SLF001
    connector._remote_id = "abc"  # noqa: SLF001

    fake_ws = FakeWebSocket([aiohttp.ClientError])

    hub_connect = await _run_listener_once(connector, fake_ws)

    assert hub_connect.await_count == 0


@pytest.fixture(autouse=True)
def fast_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace asyncio.sleep inside the module so retry-loop tests are fast.

    Applied to every test in this module; the listener tests also reach
    _reconnect() via the listener exit path and would otherwise pay the 1s
    initial backoff each.
    """

    async def _no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("aioharmony.hubconnector_websocket.asyncio.sleep", _no_sleep)


@pytest.mark.asyncio
async def test_reconnect_stops_when_disconnect_called_during_retry() -> None:
    """A concurrent hub_disconnect() must end the retry loop.

    Regression for issue #95: previously _reconnect set self._connected = False
    before its retry loop and never re-checked it, so a hub_disconnect() that
    arrived mid-retry could not stop a subsequent reconnect attempt.
    """
    connector = _make_connector()
    connector.async_close_session = AsyncMock()  # type: ignore[method-assign]

    async def fail_then_disconnect(is_reconnect: bool = False) -> bool:
        # Simulate hub_disconnect() running between retries.
        connector._connected = False  # noqa: SLF001
        return False

    hub_connect = AsyncMock(side_effect=fail_then_disconnect)
    connector.hub_connect = hub_connect  # type: ignore[method-assign]

    await connector._reconnect()  # noqa: SLF001

    # First attempt runs once, then the loop checks _connected and bails;
    # without the fix it would keep retrying forever.
    assert hub_connect.await_count == 1


@pytest.mark.asyncio
async def test_reconnect_stops_when_auto_reconnect_disabled_during_retry() -> None:
    """Flipping auto_reconnect off during retries must also stop the loop."""
    connector = _make_connector()
    connector.async_close_session = AsyncMock()  # type: ignore[method-assign]

    async def fail_then_disable(is_reconnect: bool = False) -> bool:
        connector._auto_reconnect = False  # noqa: SLF001
        return False

    hub_connect = AsyncMock(side_effect=fail_then_disable)
    connector.hub_connect = hub_connect  # type: ignore[method-assign]

    await connector._reconnect()  # noqa: SLF001

    assert hub_connect.await_count == 1


@pytest.mark.asyncio
async def test_reconnect_retries_until_success() -> None:
    """The retry loop keeps trying with is_reconnect=True after the first miss."""
    connector = _make_connector()
    connector.async_close_session = AsyncMock()  # type: ignore[method-assign]

    hub_connect = AsyncMock(side_effect=[False, False, True])
    connector.hub_connect = hub_connect  # type: ignore[method-assign]

    await connector._reconnect()  # noqa: SLF001

    assert hub_connect.await_count == 3
    # First call is the initial attempt; subsequent calls flag is_reconnect.
    first_call_kwargs = hub_connect.await_args_list[0].kwargs
    later_call_kwargs = hub_connect.await_args_list[-1].kwargs
    assert first_call_kwargs.get("is_reconnect") is False
    assert later_call_kwargs.get("is_reconnect") is True


@pytest.mark.asyncio
async def test_reconnect_does_not_clobber_connected_flag() -> None:
    """_reconnect must leave self._connected alone.

    Regression for issue #95: _reconnect used to set self._connected = False
    before the retry loop, conflating "currently connected" with "caller
    wants us connected" and defeating any later mid-retry disconnect check.
    """
    connector = _make_connector()
    connector.async_close_session = AsyncMock()  # type: ignore[method-assign]

    hub_connect = AsyncMock(return_value=True)
    connector.hub_connect = hub_connect  # type: ignore[method-assign]

    await connector._reconnect()  # noqa: SLF001

    assert connector._connected is True  # noqa: SLF001


@pytest.mark.asyncio
async def test_callbacks_property_roundtrip() -> None:
    """callbacks getter/setter is a simple pass-through."""
    connector = _make_connector()
    new_cb = ConnectorCallbackType(connect=AsyncMock(), disconnect=AsyncMock())

    connector.callbacks = new_cb

    assert connector.callbacks is new_cb


@pytest.mark.asyncio
async def test_close_delegates_to_hub_disconnect() -> None:
    """close() is a thin wrapper that just disconnects."""
    connector = _make_connector()
    connector.hub_disconnect = AsyncMock()  # type: ignore[method-assign]

    await connector.close()

    connector.hub_disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_remote_id_returns_cached_value() -> None:
    """A previously-resolved remote id short-circuits the HTTP lookup."""
    connector = _make_connector()
    connector._retrieve_hub_info = AsyncMock()  # type: ignore[method-assign]  # noqa: SLF001

    result = await connector.get_remote_id()

    assert result == "abc"
    connector._retrieve_hub_info.assert_not_called()  # noqa: SLF001


@pytest.mark.asyncio
async def test_get_remote_id_populates_from_hub_info() -> None:
    """When uncached, get_remote_id fetches and stores remoteId + domain."""
    connector = _make_connector()
    connector._remote_id = None  # noqa: SLF001
    connector._retrieve_hub_info = AsyncMock(  # type: ignore[method-assign]  # noqa: SLF001
        return_value={
            "activeRemoteId": "remote-123",
            "discoveryServer": "https://hub.example.com/path",
        }
    )

    result = await connector.get_remote_id()

    assert result == "remote-123"
    assert connector._remote_id == "remote-123"  # noqa: SLF001
    assert connector._domain == "hub.example.com"  # noqa: SLF001


@pytest.mark.asyncio
async def test_get_remote_id_falls_back_to_default_domain() -> None:
    """A discoveryServer without a netloc must leave _domain at the default."""
    connector = _make_connector()
    connector._remote_id = None  # noqa: SLF001
    connector._retrieve_hub_info = AsyncMock(  # type: ignore[method-assign]  # noqa: SLF001
        return_value={"activeRemoteId": "remote-9", "discoveryServer": ""}
    )

    await connector.get_remote_id()

    assert connector._domain == "svcs.myharmony.com"  # noqa: SLF001


@pytest.mark.asyncio
async def test_get_remote_id_handles_missing_hub_info() -> None:
    """If _retrieve_hub_info returns None, get_remote_id returns None."""
    connector = _make_connector()
    connector._remote_id = None  # noqa: SLF001
    connector._retrieve_hub_info = AsyncMock(return_value=None)  # type: ignore[method-assign]  # noqa: SLF001

    result = await connector.get_remote_id()

    assert result is None


@pytest.mark.asyncio
async def test_async_close_session_noop_when_none() -> None:
    """async_close_session is a no-op if no aiohttp session was opened."""
    connector = _make_connector()
    connector._aiohttp_session = None  # noqa: SLF001

    await connector.async_close_session()

    assert connector._aiohttp_session is None  # noqa: SLF001


@pytest.mark.asyncio
async def test_async_close_session_closes_session() -> None:
    """async_close_session closes the underlying aiohttp session."""
    connector = _make_connector()
    session = MagicMock()
    session.close = AsyncMock()
    connector._aiohttp_session = session  # noqa: SLF001

    await connector.async_close_session()

    session.close.assert_awaited_once()
    assert connector._aiohttp_session is None  # noqa: SLF001


@pytest.mark.asyncio
async def test_async_close_session_swallows_timeout() -> None:
    """A TimeoutError raised by session.close must not propagate."""
    connector = _make_connector()
    session = MagicMock()
    session.close = AsyncMock(side_effect=asyncio.TimeoutError())
    connector._aiohttp_session = session  # noqa: SLF001

    await connector.async_close_session()  # must not raise


@pytest.mark.asyncio
async def test_hub_connect_short_circuits_when_already_open() -> None:
    """An open websocket means hub_connect returns True without touching the session."""
    connector = _make_connector()
    ws = MagicMock()
    ws.closed = False
    connector._websocket = ws  # noqa: SLF001
    connector._aiohttp_session = MagicMock()  # noqa: SLF001
    # If short-circuit fails, ws_connect would be invoked - mark it un-awaitable.
    connector._aiohttp_session.ws_connect = MagicMock(  # noqa: SLF001
        side_effect=AssertionError("should not be called")
    )

    assert await connector.hub_connect() is True


@pytest.mark.asyncio
async def test_hub_connect_returns_false_without_remote_id() -> None:
    """Without a resolvable remote id, hub_connect bails out as False."""
    connector = _make_connector()
    connector._remote_id = None  # noqa: SLF001
    connector.get_remote_id = AsyncMock(return_value=None)  # type: ignore[method-assign]

    assert await connector.hub_connect() is False


@pytest.mark.asyncio
async def test_hub_connect_handles_server_timeout() -> None:
    """A ServerTimeoutError during ws_connect leaves _websocket cleared."""
    connector = _make_connector()
    session = MagicMock()
    session.ws_connect = AsyncMock(side_effect=aiohttp.ServerTimeoutError())
    connector._aiohttp_session = session  # noqa: SLF001

    assert await connector.hub_connect(is_reconnect=True) is False
    assert connector._websocket is None  # noqa: SLF001


@pytest.mark.asyncio
async def test_hub_connect_handles_client_error() -> None:
    """A ClientError during ws_connect leaves _websocket cleared."""
    connector = _make_connector()
    session = MagicMock()
    session.ws_connect = AsyncMock(side_effect=aiohttp.ClientError("nope"))
    connector._aiohttp_session = session  # noqa: SLF001

    assert await connector.hub_connect() is False
    assert connector._websocket is None  # noqa: SLF001


@pytest.mark.asyncio
async def test_hub_connect_success_fires_callback_and_starts_listener() -> None:
    """Successful ws_connect creates the listener task and notifies the connect callback."""
    connect_cb = MagicMock()
    queue: asyncio.Queue = asyncio.Queue()
    connector = HubConnector(
        ip_address="10.0.0.1",
        response_queue=queue,
        callbacks=ConnectorCallbackType(connect=connect_cb, disconnect=None),
    )
    connector._connected = False  # noqa: SLF001
    connector._remote_id = "abc"  # noqa: SLF001

    ws = MagicMock()
    ws.closed = False
    session = MagicMock()
    session.ws_connect = AsyncMock(return_value=ws)
    connector._aiohttp_session = session  # noqa: SLF001

    # Stub the listener coroutine so we don't actually loop.
    async def _idle_listener(_ws: Any) -> None:
        return None

    connector._listener = _idle_listener  # type: ignore[method-assign]  # noqa: SLF001

    assert await connector.hub_connect() is True
    assert connector._connected is True  # noqa: SLF001
    assert connector._listener_task is not None  # noqa: SLF001
    connect_cb.assert_called_once_with("10.0.0.1")

    if connector._listener_task is not None:  # noqa: SLF001
        await connector._listener_task  # noqa: SLF001


@pytest.mark.asyncio
async def test_hub_disconnect_with_no_websocket_just_flips_flag() -> None:
    """hub_disconnect without an open websocket only marks _connected False."""
    connector = _make_connector()
    connector._websocket = None  # noqa: SLF001
    connector._aiohttp_session = None  # noqa: SLF001

    await connector.hub_disconnect()

    assert connector._connected is False  # noqa: SLF001


@pytest.mark.asyncio
async def test_hub_disconnect_closes_websocket_and_session() -> None:
    """hub_disconnect closes the websocket, the session, and clears _websocket."""
    connector = _make_connector()
    ws = MagicMock()
    ws.close = AsyncMock()
    session = MagicMock()
    session.close = AsyncMock()
    connector._websocket = ws  # noqa: SLF001
    connector._aiohttp_session = session  # noqa: SLF001

    async def _idle() -> None:
        await asyncio.sleep(0)

    task = asyncio.create_task(_idle())
    connector._listener_task = task  # noqa: SLF001

    await connector.hub_disconnect()

    ws.close.assert_awaited_once()
    session.close.assert_awaited_once()
    assert connector._websocket is None  # noqa: SLF001
    assert connector._connected is False  # noqa: SLF001


@pytest.mark.asyncio
async def test_hub_disconnect_cancels_running_listener() -> None:
    """hub_disconnect cancels a still-running listener task."""
    connector = _make_connector()
    ws = MagicMock()
    ws.close = AsyncMock()
    session = MagicMock()
    session.close = AsyncMock()
    connector._websocket = ws  # noqa: SLF001
    connector._aiohttp_session = session  # noqa: SLF001

    listener_task = MagicMock()
    listener_task.done.return_value = False
    listener_task.cancel = MagicMock()
    connector._listener_task = listener_task  # noqa: SLF001

    await connector.hub_disconnect()

    listener_task.cancel.assert_called_once()


@pytest.mark.asyncio
async def test_hub_send_post_creates_background_task() -> None:
    """hub_send(post=True) hands off to hub_post via a background task."""
    connector = _make_connector()
    connector.hub_post = AsyncMock(return_value={"ok": True})  # type: ignore[method-assign]

    result = await connector.hub_send("cmd", {}, post=True)

    assert isinstance(result, asyncio.Task)
    assert await result == {"ok": True}


@pytest.mark.asyncio
async def test_hub_send_returns_none_when_connect_fails() -> None:
    """hub_send returns None if hub_connect cannot establish a session."""
    connector = _make_connector()
    connector.hub_connect = AsyncMock(return_value=False)  # type: ignore[method-assign]

    assert await connector.hub_send("cmd", {}) is None


@pytest.mark.asyncio
async def test_hub_send_returns_msgid_on_success() -> None:
    """A successful hub_send returns the message id used in the payload."""
    connector = _make_connector()
    connector.hub_connect = AsyncMock(return_value=True)  # type: ignore[method-assign]
    ws = MagicMock()
    ws.send_json = AsyncMock()
    connector._websocket = ws  # noqa: SLF001

    msgid = await connector.hub_send("cmd", {"k": "v"}, msgid="fixed-id")

    assert msgid == "fixed-id"
    ws.send_json.assert_awaited_once()
    sent_payload = ws.send_json.await_args.args[0]
    assert sent_payload["hubId"] == "abc"
    assert sent_payload["hbus"]["id"] == "fixed-id"


@pytest.mark.asyncio
async def test_hub_send_returns_none_on_client_error() -> None:
    """A ClientError during send_json returns None instead of raising."""
    connector = _make_connector()
    connector.hub_connect = AsyncMock(return_value=True)  # type: ignore[method-assign]
    ws = MagicMock()
    ws.send_json = AsyncMock(side_effect=aiohttp.ClientError("nope"))
    connector._websocket = ws  # noqa: SLF001

    assert await connector.hub_send("cmd", {}) is None


class _AsyncContextManager:
    """Minimal async-context-manager wrapper for aiohttp.ClientSession.post()."""

    def __init__(self, response: MagicMock) -> None:
        self._response = response

    async def __aenter__(self) -> MagicMock:
        return self._response

    async def __aexit__(self, *_exc: object) -> None:
        return None


@pytest.mark.asyncio
async def test_hub_post_returns_parsed_response() -> None:
    """hub_post returns the JSON body parsed by aiohttp."""
    connector = _make_connector()
    response = MagicMock()
    response.json = AsyncMock(return_value={"data": {"hello": "world"}})
    session = MagicMock()
    session.post = MagicMock(return_value=_AsyncContextManager(response))
    connector._aiohttp_session = session  # noqa: SLF001

    result = await connector.hub_post("http://hub/", {"id ": 1})

    assert result == {"data": {"hello": "world"}}


@pytest.mark.asyncio
async def test_hub_post_returns_none_on_client_error() -> None:
    """hub_post swallows aiohttp.ClientError and returns None."""
    connector = _make_connector()
    session = MagicMock()
    session.post = MagicMock(side_effect=aiohttp.ClientError("nope"))
    connector._aiohttp_session = session  # noqa: SLF001

    assert await connector.hub_post("http://hub/", {}) is None


@pytest.mark.asyncio
async def test_retrieve_hub_info_returns_inner_data() -> None:
    """_retrieve_hub_info unwraps the 'data' envelope from hub_post."""
    connector = _make_connector()
    connector.hub_post = AsyncMock(  # type: ignore[method-assign]
        return_value={"data": {"activeRemoteId": "x"}}
    )

    result = await connector._retrieve_hub_info()  # noqa: SLF001

    assert result == {"activeRemoteId": "x"}


@pytest.mark.asyncio
async def test_retrieve_hub_info_returns_none_when_post_failed() -> None:
    """_retrieve_hub_info passes None through when hub_post returned nothing."""
    connector = _make_connector()
    connector.hub_post = AsyncMock(return_value=None)  # type: ignore[method-assign]

    assert await connector._retrieve_hub_info() is None  # noqa: SLF001


@pytest.mark.asyncio
async def test_listener_skips_empty_text_message() -> None:
    """A TEXT message whose .json() is falsy must not be queued."""
    empty_text = _make_message(aiohttp.WSMsgType.TEXT)
    empty_text.json.return_value = None
    fake_ws = FakeWebSocket(
        [empty_text, _make_message(aiohttp.WSMsgType.CLOSED, data=1000)]
    )
    connector = _make_connector()

    await _run_listener_once(connector, fake_ws)

    assert connector._response_queue.empty()  # noqa: SLF001


@pytest.mark.asyncio
async def test_listener_ignores_non_text_non_close_messages() -> None:
    """Binary / ping / pong frames are ignored - the loop just keeps reading."""
    fake_ws = FakeWebSocket(
        [
            _make_message(aiohttp.WSMsgType.PING, data=b""),
            _make_message(aiohttp.WSMsgType.CLOSED, data=1000),
        ]
    )
    connector = _make_connector()

    hub_connect = await _run_listener_once(connector, fake_ws)

    assert hub_connect.await_count == 1  # CLOSED still triggers reconnect


@pytest.mark.asyncio
async def test_listener_logs_when_no_websocket_argument() -> None:
    """Calling _listener without a websocket and with no _websocket logs + exits."""
    connector = _make_connector()
    connector._websocket = None  # noqa: SLF001
    connector.hub_connect = AsyncMock(return_value=True)  # type: ignore[method-assign]
    connector.async_close_session = AsyncMock()  # type: ignore[method-assign]

    # No websocket means the loop body sees `not websocket` and breaks out
    # immediately, then triggers a reconnect attempt.
    await connector._listener(None)  # noqa: SLF001

    connector.hub_connect.assert_awaited()
