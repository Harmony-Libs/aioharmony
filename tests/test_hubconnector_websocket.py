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
