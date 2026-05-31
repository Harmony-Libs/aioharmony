"""Tests for the slixmpp connector."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
import slixmpp
from async_timeout import timeout as real_timeout
from slixmpp.exceptions import IqTimeout

import aioharmony.exceptions as aioexc
from aioharmony.const import ConnectorCallbackType
from aioharmony.hubconnector_xmpp import HubConnector


def _make_hub(
    *,
    auto_reconnect: bool = True,
    connect_cb=None,
    disconnect_cb=None,
) -> HubConnector:
    queue: asyncio.Queue = asyncio.Queue()
    return HubConnector(
        ip_address="10.0.0.42",
        response_queue=queue,
        callbacks=ConnectorCallbackType(connect_cb, disconnect_cb),
        auto_reconnect=auto_reconnect,
    )


@pytest.fixture(autouse=True)
def fast_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip backoff sleeps in xmpp reconnect path."""

    async def _no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("aioharmony.hubconnector_xmpp.asyncio.sleep", _no_sleep)


async def test_hub_connect_uses_modern_slixmpp_kwargs() -> None:
    """hub_connect must call ClientXMPP.connect with host=/port=.

    Regression for issue #93: slixmpp 1.10 replaced address=/disable_starttls=
    /use_ssl= with host=/port= and instance-level TLS toggles. The old call
    shape raises TypeError on any modern slixmpp.
    """
    hub = _make_hub()

    captured: dict = {}

    def fake_connect(self: slixmpp.ClientXMPP, *args: object, **kwargs: object) -> None:
        captured["args"] = args
        captured["kwargs"] = kwargs
        loop = asyncio.get_running_loop()
        loop.call_soon(self.event, "connected", None)

    with patch.object(slixmpp.ClientXMPP, "connect", fake_connect):
        result = await hub.hub_connect()

    assert result is True
    assert captured["args"] == ()
    assert captured["kwargs"] == {"host": "10.0.0.42", "port": 5222}
    assert hub.enable_starttls is False
    assert hub.enable_direct_tls is False

    await hub.hub_disconnect()


async def test_hub_connect_short_circuits_when_already_connected() -> None:
    """hub_connect returns True without calling slixmpp when already connected."""
    hub = _make_hub()
    hub._connected = True  # noqa: SLF001

    with patch.object(slixmpp.ClientXMPP, "connect") as connect_mock:
        result = await hub.hub_connect()

    assert result is True
    connect_mock.assert_not_called()


async def test_hub_connect_returns_false_on_iqtimeout() -> None:
    """An IqTimeout from slixmpp.connect leaves us disconnected and returns False."""
    hub = _make_hub()

    with patch.object(slixmpp.ClientXMPP, "connect", side_effect=IqTimeout(None)):
        result = await hub.hub_connect()

    assert result is False
    assert hub._connected is False  # noqa: SLF001


async def test_hub_connect_returns_false_on_oserror() -> None:
    """OSError during the connected-future wait is logged and returns False."""
    hub = _make_hub()

    def fake_connect(self: slixmpp.ClientXMPP, *args: object, **kwargs: object) -> None:
        loop = asyncio.get_running_loop()
        loop.call_soon(self.event, "connection_failed", OSError("network down"))

    with patch.object(slixmpp.ClientXMPP, "connect", fake_connect):
        result = await hub.hub_connect()

    assert result is False
    assert hub._connected is False  # noqa: SLF001


async def test_hub_connect_raises_timeout_on_connection_timeout() -> None:
    """TimeoutError on the connected-future maps to aioharmony's TimeOut."""
    hub = _make_hub()

    def fake_connect(self: slixmpp.ClientXMPP, *args: object, **kwargs: object) -> None:
        loop = asyncio.get_running_loop()
        loop.call_soon(self.event, "connection_failed", TimeoutError())

    with (
        patch.object(slixmpp.ClientXMPP, "connect", fake_connect),
        pytest.raises(aioexc.TimeOut),
    ):
        await hub.hub_connect()

    assert hub._connected is False  # noqa: SLF001


async def test_hub_connect_returns_false_on_stray_cancellederror() -> None:
    """A CancelledError that isn't a real task-cancel returns False, no raise."""
    hub = _make_hub()

    def fake_connect(self: slixmpp.ClientXMPP, *args: object, **kwargs: object) -> None:
        loop = asyncio.get_running_loop()
        loop.call_soon(self.event, "connection_failed", asyncio.CancelledError())

    with patch.object(slixmpp.ClientXMPP, "connect", fake_connect):
        result = await hub.hub_connect()

    assert result is False
    assert hub._connected is False  # noqa: SLF001


async def test_hub_connect_reraises_when_task_is_being_cancelled() -> None:
    """If the surrounding task was cancelled, CancelledError propagates."""
    hub = _make_hub()

    def fake_connect(self: slixmpp.ClientXMPP, *args: object, **kwargs: object) -> None:
        task = asyncio.current_task()
        assert task is not None
        task.cancel()

    with (
        patch.object(slixmpp.ClientXMPP, "connect", fake_connect),
        pytest.raises(asyncio.CancelledError),
    ):
        await hub.hub_connect()

    assert hub._connected is False  # noqa: SLF001


async def test_hub_disconnect_is_noop_when_not_connected() -> None:
    """hub_disconnect must exit early if there is nothing to tear down."""
    hub = _make_hub()
    with patch.object(slixmpp.ClientXMPP, "disconnect") as disconnect_mock:
        await hub.hub_disconnect()
    disconnect_mock.assert_not_called()


async def test_hub_disconnect_drives_disconnected_future() -> None:
    """hub_disconnect resolves once slixmpp fires the 'disconnected' event."""
    hub = _make_hub()
    hub._connected = True  # noqa: SLF001

    def fake_disconnect(self: slixmpp.ClientXMPP) -> None:
        loop = asyncio.get_running_loop()
        loop.call_soon(self.event, "disconnected", None)

    with patch.object(slixmpp.ClientXMPP, "disconnect", fake_disconnect):
        await hub.hub_disconnect()

    assert hub._connected is False  # noqa: SLF001


async def test_hub_disconnect_raises_timeout_when_event_never_fires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If slixmpp never emits 'disconnected', hub_disconnect raises TimeOut."""
    hub = _make_hub()
    hub._connected = True  # noqa: SLF001

    monkeypatch.setattr(
        "aioharmony.hubconnector_xmpp.timeout", lambda _delay: real_timeout(0)
    )

    with (
        patch.object(slixmpp.ClientXMPP, "disconnect"),
        pytest.raises(aioexc.TimeOut),
    ):
        await hub.hub_disconnect()


async def test_close_calls_hub_disconnect() -> None:
    """close() must funnel through hub_disconnect."""
    hub = _make_hub()

    async def fake_hub_disconnect() -> None:
        fake_hub_disconnect.called = True  # type: ignore[attr-defined]

    fake_hub_disconnect.called = False  # type: ignore[attr-defined]
    hub.hub_disconnect = fake_hub_disconnect  # type: ignore[method-assign]
    await hub.close()
    assert fake_hub_disconnect.called is True  # type: ignore[attr-defined]


async def test_connected_handler_sets_flag_and_fires_callback() -> None:
    """_connected_handler flips _connected and invokes the connect callback."""
    seen: list[str] = []

    def on_connect(ip: str) -> None:
        seen.append(ip)

    hub = _make_hub(connect_cb=on_connect)
    hub._connected_handler(None)  # noqa: SLF001

    assert hub._connected is True  # noqa: SLF001
    assert seen == ["10.0.0.42"]


async def test_disconnected_handler_returns_when_not_connected() -> None:
    """If _connected is False (user disconnected), no reconnect is attempted."""
    seen: list[str] = []
    hub = _make_hub(disconnect_cb=seen.append)

    with patch.object(HubConnector, "hub_connect") as hub_connect:
        await hub._disconnected_handler(None)  # noqa: SLF001

    hub_connect.assert_not_called()
    assert seen == ["10.0.0.42"]


async def test_disconnected_handler_returns_when_auto_reconnect_disabled() -> None:
    """auto_reconnect=False must suppress reconnect even if we were connected."""
    hub = _make_hub(auto_reconnect=False)
    hub._connected = True  # noqa: SLF001

    with patch.object(HubConnector, "hub_connect") as hub_connect:
        await hub._disconnected_handler(None)  # noqa: SLF001

    hub_connect.assert_not_called()


async def test_disconnected_handler_reconnects_on_first_attempt() -> None:
    """The retry loop exits as soon as hub_connect returns True."""
    hub = _make_hub()
    hub._connected = True  # noqa: SLF001

    hub_connect_calls: list[bool] = []

    async def fake_hub_connect(is_reconnect: bool = False) -> bool:
        hub_connect_calls.append(is_reconnect)
        return True

    hub.hub_connect = fake_hub_connect  # type: ignore[method-assign]
    hub._deregister_handlers = MagicMock()  # type: ignore[method-assign]  # noqa: SLF001
    hub._init_super = MagicMock()  # type: ignore[method-assign]  # noqa: SLF001

    await hub._disconnected_handler(None)  # noqa: SLF001

    assert hub_connect_calls == [False]
    hub._deregister_handlers.assert_called_once()  # noqa: SLF001
    hub._init_super.assert_called_once()  # noqa: SLF001


async def test_disconnected_handler_retries_after_iqtimeout_and_failure() -> None:
    """IqTimeout and False both retry; success on the third attempt exits."""
    hub = _make_hub()
    hub._connected = True  # noqa: SLF001

    attempts = iter([IqTimeout(None), False, True])
    flags: list[bool] = []

    async def fake_hub_connect(is_reconnect: bool = False) -> bool:
        flags.append(is_reconnect)
        outcome = next(attempts)
        if isinstance(outcome, IqTimeout):
            raise outcome
        return outcome

    hub.hub_connect = fake_hub_connect  # type: ignore[method-assign]
    hub._deregister_handlers = MagicMock()  # type: ignore[method-assign]  # noqa: SLF001
    hub._init_super = MagicMock()  # type: ignore[method-assign]  # noqa: SLF001

    await hub._disconnected_handler(None)  # noqa: SLF001

    assert flags == [False, True, True]


async def test_disconnected_handler_stops_when_disconnect_requested_mid_reconnect() -> (
    None
):
    """A hub_disconnect() during the retry loop stops further reconnect attempts."""
    hub = _make_hub()
    hub._connected = True  # noqa: SLF001

    flags: list[bool] = []

    async def fake_hub_connect(is_reconnect: bool = False) -> bool:
        flags.append(is_reconnect)
        hub._disconnect_requested = True  # noqa: SLF001
        return False

    hub.hub_connect = fake_hub_connect  # type: ignore[method-assign]
    hub._deregister_handlers = MagicMock()  # type: ignore[method-assign]  # noqa: SLF001
    hub._init_super = MagicMock()  # type: ignore[method-assign]  # noqa: SLF001

    await hub._disconnected_handler(None)  # noqa: SLF001

    assert flags == [False]


async def test_disconnected_handler_stops_when_auto_reconnect_cleared_mid_reconnect() -> (
    None
):
    """Clearing auto_reconnect during the retry loop stops further attempts."""
    hub = _make_hub()
    hub._connected = True  # noqa: SLF001

    flags: list[bool] = []

    async def fake_hub_connect(is_reconnect: bool = False) -> bool:
        flags.append(is_reconnect)
        hub._auto_reconnect = False  # noqa: SLF001
        return False

    hub.hub_connect = fake_hub_connect  # type: ignore[method-assign]
    hub._deregister_handlers = MagicMock()  # type: ignore[method-assign]  # noqa: SLF001
    hub._init_super = MagicMock()  # type: ignore[method-assign]  # noqa: SLF001

    await hub._disconnected_handler(None)  # noqa: SLF001

    assert flags == [False]


async def test_disconnected_handler_backoff_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reconnect backoff keeps the 1, 1, 2, 4 cadence and skips sleep on success."""
    hub = _make_hub()
    hub._connected = True  # noqa: SLF001

    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("aioharmony.hubconnector_xmpp.asyncio.sleep", record_sleep)

    outcomes = iter([False, False, False, True])

    async def fake_hub_connect(is_reconnect: bool = False) -> bool:
        return next(outcomes)

    hub.hub_connect = fake_hub_connect  # type: ignore[method-assign]
    hub._deregister_handlers = MagicMock()  # type: ignore[method-assign]  # noqa: SLF001
    hub._init_super = MagicMock()  # type: ignore[method-assign]  # noqa: SLF001

    await hub._disconnected_handler(None)  # noqa: SLF001

    assert delays == [1, 1, 2, 4]


async def test_disconnected_handler_stops_before_backoff_when_disconnect_mid_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disconnect during hub_connect() exits before the backoff sleep."""
    hub = _make_hub()
    hub._connected = True  # noqa: SLF001

    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("aioharmony.hubconnector_xmpp.asyncio.sleep", record_sleep)

    async def fake_hub_connect(is_reconnect: bool = False) -> bool:
        hub._disconnect_requested = True  # noqa: SLF001
        return False

    hub.hub_connect = fake_hub_connect  # type: ignore[method-assign]
    hub._deregister_handlers = MagicMock()  # type: ignore[method-assign]  # noqa: SLF001
    hub._init_super = MagicMock()  # type: ignore[method-assign]  # noqa: SLF001

    await hub._disconnected_handler(None)  # noqa: SLF001

    assert delays == [1]


async def test_disconnected_handler_stops_at_loop_top_when_disconnect_before_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disconnect during the pre-loop sleep stops before the first reconnect attempt."""
    hub = _make_hub()
    hub._connected = True  # noqa: SLF001

    flags: list[bool] = []

    async def set_intent_during_sleep(_delay: float) -> None:
        hub._disconnect_requested = True  # noqa: SLF001

    monkeypatch.setattr(
        "aioharmony.hubconnector_xmpp.asyncio.sleep", set_intent_during_sleep
    )

    async def fake_hub_connect(is_reconnect: bool = False) -> bool:
        flags.append(is_reconnect)
        return False

    hub.hub_connect = fake_hub_connect  # type: ignore[method-assign]
    hub._deregister_handlers = MagicMock()  # type: ignore[method-assign]  # noqa: SLF001
    hub._init_super = MagicMock()  # type: ignore[method-assign]  # noqa: SLF001

    await hub._disconnected_handler(None)  # noqa: SLF001

    assert flags == []


async def test_hub_disconnect_sets_disconnect_requested_flag() -> None:
    """hub_disconnect records intent even when nothing is connected."""
    hub = _make_hub()

    await hub.hub_disconnect()

    assert hub._disconnect_requested is True  # noqa: SLF001


async def test_hub_connect_clears_disconnect_requested_on_success() -> None:
    """A successful connect resets the disconnect-requested flag."""
    hub = _make_hub()
    hub._disconnect_requested = True  # noqa: SLF001

    def fake_connect(self: slixmpp.ClientXMPP, *args: object, **kwargs: object) -> None:
        loop = asyncio.get_running_loop()
        loop.call_soon(self.event, "connected", None)

    with patch.object(slixmpp.ClientXMPP, "connect", fake_connect):
        result = await hub.hub_connect()

    assert result is True
    assert hub._disconnect_requested is False  # noqa: SLF001
    await hub.hub_disconnect()


async def test_listener_message_received_parses_json() -> None:
    """JSON payloads land in the response queue as a dict."""
    hub = _make_hub()

    msg = MagicMock()
    msg.text = '{"hello": "world"}'
    msg.attrib = {"xmlns": "ns", "mime": "cmd", "type": "t"}

    event = MagicMock()
    event.get_payload.return_value = [msg]
    event.get.return_value = "msg-1"

    hub._listener_message_received(event)  # noqa: SLF001

    response = hub._response_queue.get_nowait()  # noqa: SLF001
    assert response["data"] == {"hello": "world"}
    assert response["id"] == "msg-1"
    assert response["cmd"] == "cmd"
    assert response["code"] == 0


async def test_listener_message_received_falls_back_to_key_value_pairs() -> None:
    """Non-JSON `key=value:key=value` payloads still parse into a dict."""
    hub = _make_hub()

    msg = MagicMock()
    msg.text = "status=running:remoteId=abc"
    msg.attrib = {"xmlns": "ns", "mime": "cmd", "type": "t"}

    event = MagicMock()
    event.get_payload.return_value = [msg]
    event.get.return_value = "msg-2"

    hub._listener_message_received(event)  # noqa: SLF001

    response = hub._response_queue.get_nowait()  # noqa: SLF001
    assert response["data"] == {"status": "running", "remoteId": "abc"}


async def test_listener_message_received_handles_empty_payload() -> None:
    """An empty payload list logs and drops the message without queueing."""
    hub = _make_hub()

    event = MagicMock()
    event.get_payload.return_value = []

    hub._listener_message_received(event)  # noqa: SLF001

    assert hub._response_queue.empty()  # noqa: SLF001


async def test_listener_message_received_handles_errorcode_attrib() -> None:
    """A non-zero errorcode propagates through to the response dict."""
    hub = _make_hub()

    msg = MagicMock()
    msg.text = ""
    msg.attrib = {
        "xmlns": "ns",
        "mime": "cmd",
        "type": "error",
        "errorcode": "500",
        "errorstring": "boom",
    }

    event = MagicMock()
    event.get_payload.return_value = [msg]
    event.get.return_value = "msg-3"

    hub._listener_message_received(event)  # noqa: SLF001

    response = hub._response_queue.get_nowait()  # noqa: SLF001
    assert response["code"] == 500
    assert response["codestring"] == "boom"
    assert response["data"] == {}


async def test_hub_send_returns_none_when_connect_fails() -> None:
    """hub_send bails out if hub_connect cannot establish a session."""
    hub = _make_hub()

    async def fake_hub_connect(is_reconnect: bool = False) -> bool:
        return False

    hub.hub_connect = fake_hub_connect  # type: ignore[method-assign]
    result = await hub.hub_send("get_config", params={"key": "value"})
    assert result is None


@pytest.mark.parametrize(
    ("iq_type", "factory"),
    [
        ("query", "make_iq_query"),
        ("set", "make_iq_set"),
        ("result", "make_iq_result"),
        ("get", "make_iq_get"),
    ],
)
async def test_hub_send_builds_payload_for_iq_type(iq_type: str, factory: str) -> None:
    """hub_send dispatches to the right make_iq_* factory and returns a msgid."""
    hub = _make_hub()

    async def fake_hub_connect(is_reconnect: bool = False) -> bool:
        return True

    hub.hub_connect = fake_hub_connect  # type: ignore[method-assign]

    iq_stanza = MagicMock()
    sent_future = asyncio.get_running_loop().create_future()
    sent_future.set_result(None)
    iq_stanza.send.return_value = sent_future

    with patch.object(HubConnector, factory, return_value=iq_stanza, create=True):
        msgid = await hub.hub_send(
            "harmony.engine?config", iq_type=iq_type, params={"k": "v"}
        )

    assert msgid is not None
    # The stanza id must equal the returned msgid (the function sets it).
    iq_stanza.__setitem__.assert_any_call("id", msgid)
    iq_stanza.send.assert_called_once_with(timeout=1)


async def test_hub_send_error_iq_passes_msgid_as_id_kwarg() -> None:
    """The 'error' branch uses make_iq_error(id=msgid) — verify the kwarg."""
    hub = _make_hub()

    async def fake_hub_connect(is_reconnect: bool = False) -> bool:
        return True

    hub.hub_connect = fake_hub_connect  # type: ignore[method-assign]

    iq_stanza = MagicMock()
    sent_future = asyncio.get_running_loop().create_future()
    sent_future.set_result(None)
    iq_stanza.send.return_value = sent_future

    with patch.object(
        HubConnector, "make_iq_error", return_value=iq_stanza, create=True
    ) as make_iq_error:
        msgid = await hub.hub_send("cmd", iq_type="error", params={"a": "b"})

    make_iq_error.assert_called_once_with(id=msgid)


async def test_hub_send_joins_multiple_params_with_colon() -> None:
    """Multiple params serialize as `k1=v1:k2=v2` in payload text."""
    hub = _make_hub()

    async def fake_hub_connect(is_reconnect: bool = False) -> bool:
        return True

    hub.hub_connect = fake_hub_connect  # type: ignore[method-assign]

    iq_stanza = MagicMock()
    sent_future = asyncio.get_running_loop().create_future()
    sent_future.set_result(None)
    iq_stanza.send.return_value = sent_future
    captured_payload = {}

    def capture_payload(payload):
        captured_payload["text"] = payload.text

    iq_stanza.set_payload.side_effect = capture_payload

    with patch.object(HubConnector, "make_iq_get", return_value=iq_stanza, create=True):
        await hub.hub_send("cmd", params={"a": "1", "b": "2"})

    # dicts preserve insertion order on py3.7+, so a=1:b=2 is the expected text.
    assert captured_payload["text"] == "a=1:b=2"


async def test_callbacks_setter_replaces_callbacks() -> None:
    """The callbacks property round-trips a fresh ConnectorCallbackType."""
    hub = _make_hub()
    new = ConnectorCallbackType(connect=lambda _ip: None, disconnect=None)
    hub.callbacks = new
    assert hub.callbacks is new
