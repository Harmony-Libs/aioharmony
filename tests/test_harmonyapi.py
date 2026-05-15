"""Tests for the high-level HarmonyAPI wrapper."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from aioharmony import harmonyapi as harmonyapi_module
from aioharmony.const import (
    ClientCallbackType,
    ClientConfigType,
    SendCommandDevice,
    SendCommandResponse,
)
from aioharmony.handler import Handler


def _make_config(
    *,
    info: dict | None = None,
    hub_state: dict | None = None,
    config: dict | None = None,
) -> ClientConfigType:
    return ClientConfigType(
        config=config if config is not None else {},
        info=info if info is not None else {},
        discover_info={},
        hub_state=hub_state if hub_state is not None else {},
        config_version=None,
        activities=[],
        devices=[],
    )


@pytest.fixture
def fake_client() -> MagicMock:
    """Return a MagicMock standing in for HarmonyClient."""
    client = MagicMock(name="HarmonyClient")
    client.ip_address = "10.0.0.5"
    client.protocol = "WEBSOCKETS"
    client.name = "Living Room"
    client.hub_config = _make_config()
    client.current_activity_id = "12345"
    client.get_activity_name.return_value = "Watch TV"
    client.callbacks = ClientCallbackType(None, None, None, None, None)
    # Async methods.
    client.connect = AsyncMock(return_value=True)
    client.close = AsyncMock(return_value=None)
    client.send_to_hub = AsyncMock()
    client.refresh_info_from_hub = AsyncMock()
    client.start_activity = AsyncMock()
    client.send_commands = AsyncMock()
    return client


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch, fake_client: MagicMock):
    """Construct a HarmonyAPI wired to ``fake_client``.

    The patch targets the class binding HarmonyAPI.__init__ references.
    """
    factory = MagicMock(return_value=fake_client)
    monkeypatch.setattr(harmonyapi_module, "HarmonyClient", factory)

    instance = harmonyapi_module.HarmonyAPI(
        ip_address="10.0.0.5",
        protocol="WEBSOCKETS",
        callbacks=None,
        loop=MagicMock(),
    )
    return instance, factory


def test_init_forwards_arguments(api: tuple, fake_client: MagicMock) -> None:
    _instance, factory = api
    factory.assert_called_once()
    kwargs = factory.call_args.kwargs
    assert kwargs["ip_address"] == "10.0.0.5"
    assert kwargs["protocol"] == "WEBSOCKETS"
    assert kwargs["callbacks"] is None
    assert kwargs["loop"] is not None


def test_init_without_loop_uses_running_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """When no loop is given the wrapper must call asyncio.get_running_loop."""
    fake_loop = MagicMock(name="loop")
    monkeypatch.setattr(
        harmonyapi_module.asyncio, "get_running_loop", lambda: fake_loop
    )
    factory = MagicMock()
    monkeypatch.setattr(harmonyapi_module, "HarmonyClient", factory)

    harmonyapi_module.HarmonyAPI(ip_address="10.0.0.5")

    assert factory.call_args.kwargs["loop"] is fake_loop


def test_simple_properties_proxy(api: tuple, fake_client: MagicMock) -> None:
    instance, _ = api
    assert instance.ip_address == "10.0.0.5"
    assert instance.protocol == "WEBSOCKETS"
    assert instance.name == "Living Room"
    assert instance.hub_config is fake_client.hub_config


def test_email_account_fw_hub_id(api: tuple, fake_client: MagicMock) -> None:
    instance, _ = api
    fake_client.hub_config = _make_config(
        info={
            "email": "user@example.com",
            "accountId": "acc-1",
            "activeRemoteId": "hub-9",
        },
        hub_state={"hubSwVersion": "4.15.250"},
    )
    assert instance.email == "user@example.com"
    assert instance.account_id == "acc-1"
    assert instance.fw_version == "4.15.250"
    assert instance.hub_id == "hub-9"


def test_email_missing_keys_returns_none(api: tuple, fake_client: MagicMock) -> None:
    instance, _ = api
    fake_client.hub_config = _make_config()
    assert instance.email is None
    assert instance.account_id is None
    assert instance.fw_version is None
    assert instance.hub_id is None


def test_current_activity_returns_id_and_name(
    api: tuple, fake_client: MagicMock
) -> None:
    instance, _ = api
    fake_client.current_activity_id = "777"
    fake_client.get_activity_name.return_value = "Movie"
    assert instance.current_activity == ("777", "Movie")
    fake_client.get_activity_name.assert_called_with("777")


def test_config_property_returns_inner_config(
    api: tuple, fake_client: MagicMock
) -> None:
    instance, _ = api
    expected = {"activity": [], "device": []}
    fake_client.hub_config = _make_config(config=expected)
    assert instance.config is expected


def test_json_config_builds_activity_and_device_maps(
    api: tuple, fake_client: MagicMock
) -> None:
    instance, _ = api
    fake_client.hub_config = _make_config(
        config={
            "activity": [
                {"id": "1", "label": "Watch TV"},
                {"id": "2", "label": "Listen Music"},
            ],
            "device": [
                {
                    "id": "100",
                    "label": "TV",
                    "controlGroup": [
                        {
                            "function": [
                                {"action": '{"command": "PowerToggle"}'},
                                {"action": '{"command": "VolumeUp"}'},
                            ]
                        }
                    ],
                },
                {
                    "id": "200",
                    "label": "AVR",
                    "controlGroup": [
                        {"function": [{"action": "null"}]},
                    ],
                },
            ],
        }
    )

    out = instance.json_config

    assert out["Activities"] == {"1": "Watch TV", "2": "Listen Music"}
    assert out["Devices"]["TV"] == {
        "id": "100",
        "commands": ["PowerToggle", "VolumeUp"],
    }
    # An action of "null" must be filtered out: empty command list remains.
    assert out["Devices"]["AVR"] == {"id": "200", "commands": []}


def test_json_config_empty_when_config_missing(
    api: tuple, fake_client: MagicMock
) -> None:
    instance, _ = api
    fake_client.hub_config = _make_config(config={})
    assert instance.json_config == {"Activities": {}, "Devices": {}}


def test_callbacks_get_and_set(api: tuple, fake_client: MagicMock) -> None:
    instance, _ = api
    new_cb = ClientCallbackType(None, None, None, None, None)
    instance.callbacks = new_cb
    assert fake_client.callbacks is new_cb
    # And re-reading proxies through to the client.
    assert instance.callbacks is new_cb


def test_lookup_helpers_proxy(api: tuple, fake_client: MagicMock) -> None:
    instance, _ = api
    fake_client.get_activity_id.return_value = "12"
    fake_client.get_activity_name.return_value = "Watch TV"
    fake_client.get_device_id.return_value = "100"
    fake_client.get_device_name.return_value = "TV"

    assert instance.get_activity_id("Watch TV") == "12"
    fake_client.get_activity_id.assert_called_with(activity_name="Watch TV")

    assert instance.get_activity_name("12") == "Watch TV"
    fake_client.get_activity_name.assert_called_with(activity_id="12")

    assert instance.get_device_id("TV") == "100"
    fake_client.get_device_id.assert_called_with(device_name="TV")

    assert instance.get_device_name("100") == "TV"
    fake_client.get_device_name.assert_called_with(device_id="100")


@pytest.mark.asyncio
async def test_connect_close_proxy(api: tuple, fake_client: MagicMock) -> None:
    instance, _ = api
    assert await instance.connect() is True
    fake_client.connect.assert_awaited_once()
    await instance.close()
    fake_client.close.assert_awaited_once()


def test_register_and_unregister_handler_proxy(
    api: tuple, fake_client: MagicMock
) -> None:
    instance, _ = api
    fake_client.register_handler.return_value = "uuid-abc"
    fake_client.unregister_handler.return_value = True

    handler = Handler(handler_obj=lambda *_a, **_k: None)
    expiration = timedelta(seconds=5)
    result = instance.register_handler(
        handler=handler, msgid="m-1", expiration=expiration
    )
    assert result == "uuid-abc"
    fake_client.register_handler.assert_called_once_with(
        handler=handler, msgid="m-1", expiration=expiration
    )

    assert instance.unregister_handler("uuid-abc") is True
    fake_client.unregister_handler.assert_called_once_with(handler_uuid="uuid-abc")


@pytest.mark.asyncio
async def test_sync_success(api: tuple, fake_client: MagicMock) -> None:
    instance, _ = api
    fake_client.send_to_hub.return_value = {"code": 200}

    assert await instance.sync() is True

    fake_client.send_to_hub.assert_awaited_once_with(command="sync")
    fake_client.refresh_info_from_hub.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_returns_false_when_no_response(
    api: tuple, fake_client: MagicMock
) -> None:
    instance, _ = api
    fake_client.send_to_hub.return_value = None

    assert await instance.sync() is False
    fake_client.refresh_info_from_hub.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_returns_false_when_bad_code(
    api: tuple, fake_client: MagicMock
) -> None:
    instance, _ = api
    fake_client.send_to_hub.return_value = {"code": 500}

    assert await instance.sync() is False
    fake_client.refresh_info_from_hub.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_activity_proxy(api: tuple, fake_client: MagicMock) -> None:
    instance, _ = api
    fake_client.start_activity.return_value = (True, None, None)
    assert await instance.start_activity("42") == (True, None, None)
    fake_client.start_activity.assert_awaited_once_with(activity_id="42")


@pytest.mark.asyncio
async def test_send_commands_wraps_single_command(
    api: tuple, fake_client: MagicMock
) -> None:
    instance, _ = api
    command = SendCommandDevice(device=100, command="VolumeUp", delay=0.0)
    fake_client.send_commands.return_value = [
        SendCommandResponse(command=command, code="200", msg="ok")
    ]

    result = await instance.send_commands(command)

    assert len(result) == 1
    fake_client.send_commands.assert_awaited_once()
    sent_commands = fake_client.send_commands.await_args.kwargs["commands"]
    assert sent_commands == [command]


@pytest.mark.asyncio
async def test_send_commands_passes_list_through(
    api: tuple, fake_client: MagicMock
) -> None:
    instance, _ = api
    commands = [
        SendCommandDevice(device=100, command="VolumeUp", delay=0.0),
        SendCommandDevice(device=100, command="VolumeUp", delay=0.5),
    ]
    fake_client.send_commands.return_value = []

    await instance.send_commands(commands)

    sent = fake_client.send_commands.await_args.kwargs["commands"]
    assert sent is commands


@pytest.mark.asyncio
async def test_power_off_returns_first_tuple_element(
    api: tuple, fake_client: MagicMock
) -> None:
    instance, _ = api
    fake_client.start_activity.return_value = (True, "ok", None)
    assert await instance.power_off() is True
    fake_client.start_activity.assert_awaited_once_with(activity_id=-1)


@pytest.mark.asyncio
async def test_power_off_false_when_start_activity_fails(
    api: tuple, fake_client: MagicMock
) -> None:
    instance, _ = api
    fake_client.start_activity.return_value = (False, "err", None)
    assert await instance.power_off() is False


@pytest.mark.asyncio
async def test_change_channel_success(api: tuple, fake_client: MagicMock) -> None:
    instance, _ = api
    fake_client.send_to_hub.return_value = {"code": 200}
    assert await instance.change_channel(42) is True
    fake_client.send_to_hub.assert_awaited_once_with(
        command="change_channel",
        params={"timestamp": 0, "channel": "42"},
    )


@pytest.mark.asyncio
async def test_change_channel_returns_false_on_empty_response(
    api: tuple, fake_client: MagicMock
) -> None:
    instance, _ = api
    fake_client.send_to_hub.return_value = None
    assert await instance.change_channel(42) is False


@pytest.mark.asyncio
async def test_change_channel_returns_false_on_bad_code(
    api: tuple, fake_client: MagicMock
) -> None:
    instance, _ = api
    fake_client.send_to_hub.return_value = {"code": 500}
    assert await instance.change_channel(42) is False
