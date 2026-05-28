"""Tests for the ``aioharmony.__main__`` CLI entry point."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import aioharmony.__main__ as cli
import aioharmony.exceptions as harmony_exceptions


@pytest.fixture(autouse=True)
def _restore_root_logger() -> Iterator[None]:
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    try:
        yield
    finally:
        for h in list(root.handlers):
            if h not in saved_handlers:
                root.removeHandler(h)
        for h in saved_handlers:
            if h not in root.handlers:
                root.addHandler(h)
        root.setLevel(saved_level)


def _make_args(**overrides: object) -> SimpleNamespace:
    base: dict[str, object] = {
        "show_responses": False,
        "wait": 0,
        "protocol": None,
        "loglevel": "ERROR",
        "logmodules": None,
        "discover": False,
        "harmony_ip": "10.0.0.5",
        "activity": None,
        "device_id": "1",
        "command": "Play",
        "commands": "Play Stop",
        "repeat_num": 1,
        "delay_secs": 0.0,
        "hold_secs": 0.0,
        "channel": "5",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_logging_filter_exact_match_passes() -> None:
    rec = logging.LogRecord(
        "aioharmony.harmonyclient", logging.INFO, "f", 1, "m", None, None
    )
    assert cli.LoggingFilter(["aioharmony.harmonyclient"]).filter(rec) is True


def test_logging_filter_regex_match_passes() -> None:
    rec = logging.LogRecord("aioharmony.x.y", logging.INFO, "f", 1, "m", None, None)
    assert cli.LoggingFilter(["aioharmony.*"]).filter(rec) is True


def test_logging_filter_no_match_filtered() -> None:
    rec = logging.LogRecord("other.module", logging.INFO, "f", 1, "m", None, None)
    assert cli.LoggingFilter(["aioharmony"]).filter(rec) is False


async def test_get_client_connects_successfully(
    monkeypatch: pytest.MonkeyPatch,
    mock_client: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    instance = MagicMock(return_value=mock_client)
    monkeypatch.setattr(cli, "HarmonyAPI", instance)

    result = await cli.get_client("10.0.0.5", "WEBSOCKETS", show_responses=True)

    assert result is mock_client
    mock_client.register_handler.assert_called_once()
    out = capsys.readouterr().out
    assert "Trying to connect" in out
    assert "Connected to HUB" in out


async def test_get_client_connect_returns_false(
    monkeypatch: pytest.MonkeyPatch,
    mock_client: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mock_client.connect = AsyncMock(return_value=False)
    monkeypatch.setattr(cli, "HarmonyAPI", MagicMock(return_value=mock_client))

    result = await cli.get_client("10.0.0.5", "WEBSOCKETS", show_responses=False)

    assert result is None
    assert "An issue occurred" in capsys.readouterr().out


async def test_get_client_connection_refused(
    monkeypatch: pytest.MonkeyPatch,
    mock_client: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mock_client.connect = AsyncMock(side_effect=ConnectionRefusedError())
    monkeypatch.setattr(cli, "HarmonyAPI", MagicMock(return_value=mock_client))

    result = await cli.get_client("10.0.0.5", "WEBSOCKETS", show_responses=False)

    assert result is None
    out = capsys.readouterr().out
    assert "Failed to connect" in out


async def test_show_config(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    await cli.show_config(mock_client, _make_args())
    assert "Living Room" in capsys.readouterr().out


async def test_show_config_missing(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    mock_client.config = None
    await cli.show_config(mock_client, _make_args())
    assert "problem retrieving" in capsys.readouterr().out


async def test_show_detailed_config(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    await cli.show_detailed_config(mock_client, _make_args())
    assert "Living Room" in capsys.readouterr().out


async def test_show_detailed_config_missing(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    mock_client.hub_config = None
    await cli.show_detailed_config(mock_client, _make_args())
    assert "problem retrieving" in capsys.readouterr().out


async def test_show_current_activity_named(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    await cli.show_current_activity(mock_client, _make_args())
    assert "Watch TV" in capsys.readouterr().out


async def test_show_current_activity_id_only(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    mock_client.current_activity = (42, None)
    await cli.show_current_activity(mock_client, _make_args())
    assert "activity_id" in capsys.readouterr().out


async def test_show_current_activity_missing(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    mock_client.current_activity = (None, None)
    await cli.show_current_activity(mock_client, _make_args())
    assert "Unable to retrieve" in capsys.readouterr().out


async def test_start_activity_no_activity(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    await cli.start_activity(mock_client, _make_args(activity=None))
    assert "No activity provided" in capsys.readouterr().out


async def test_start_activity_numeric_id(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    await cli.start_activity(mock_client, _make_args(activity="42"))
    mock_client.start_activity.assert_awaited_with("42")
    assert "Started Activity" in capsys.readouterr().out


async def test_start_activity_named(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    mock_client.get_activity_id.return_value = "9001"
    await cli.start_activity(mock_client, _make_args(activity="Watch TV"))
    mock_client.start_activity.assert_awaited_with("9001")
    assert "Found activity named" in capsys.readouterr().out


async def test_start_activity_invalid(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    mock_client.get_activity_id.return_value = None
    await cli.start_activity(mock_client, _make_args(activity="Nonsense"))
    assert "Invalid activity" in capsys.readouterr().out


async def test_start_activity_failed(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    mock_client.start_activity = AsyncMock(return_value=(False, "boom"))
    await cli.start_activity(mock_client, _make_args(activity="42"))
    assert "Activity start failed" in capsys.readouterr().out


async def test_start_activity_power_off_id(mock_client: MagicMock) -> None:
    await cli.start_activity(mock_client, _make_args(activity="-1"))
    mock_client.start_activity.assert_awaited_with("-1")


async def test_power_off_ok(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    await cli.power_off(mock_client, _make_args())
    assert "Powered Off" in capsys.readouterr().out


async def test_power_off_failed(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    mock_client.power_off = AsyncMock(return_value=False)
    await cli.power_off(mock_client, _make_args())
    assert "Power off failed" in capsys.readouterr().out


async def test_change_channel_ok(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    await cli.change_channel(mock_client, _make_args(channel="7"))
    mock_client.change_channel.assert_awaited_with("7")
    assert "Changed to channel 7" in capsys.readouterr().out


async def test_change_channel_failed(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    mock_client.change_channel = AsyncMock(return_value=False)
    await cli.change_channel(mock_client, _make_args(channel="7"))
    assert "Change to channel 7 failed" in capsys.readouterr().out


async def test_set_sleep_timer_ok(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    await cli.set_sleep_timer(mock_client, _make_args(interval=300))
    mock_client.set_sleep_timer.assert_awaited_with(300)
    assert "Sleep timer set to 300" in capsys.readouterr().out


async def test_set_sleep_timer_failed(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    mock_client.set_sleep_timer = AsyncMock(return_value=False)
    await cli.set_sleep_timer(mock_client, _make_args(interval=300))
    assert "Sleep timer set to 300 failed" in capsys.readouterr().out


async def test_sync_ok(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    await cli.sync(mock_client, _make_args())
    assert "Sync complete" in capsys.readouterr().out


async def test_sync_failed(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    mock_client.sync = AsyncMock(return_value=False)
    await cli.sync(mock_client, _make_args())
    assert "Sync failed" in capsys.readouterr().out


async def test_just_listen_registers_handler(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    await cli.just_listen(mock_client, _make_args(show_responses=False))
    mock_client.register_handler.assert_called_once()
    assert "Starting to listen" in capsys.readouterr().out


async def test_just_listen_skips_when_already_showing(mock_client: MagicMock) -> None:
    await cli.just_listen(mock_client, _make_args(show_responses=True))
    mock_client.register_handler.assert_not_called()


async def test_just_listen_callback_prints_message(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    await cli.just_listen(mock_client, _make_args(show_responses=False))
    handler = mock_client.register_handler.call_args.kwargs["handler"]
    capsys.readouterr()
    handler.handler_obj("hello-world")
    assert "hello-world" in capsys.readouterr().out


async def test_listen_for_new_activities_starting(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    await cli.listen_for_new_activities(mock_client, _make_args())
    new_callbacks = mock_client.callbacks
    new_callbacks.new_activity_starting((7, "Game"))
    new_callbacks.new_activity_starting((-1, "PowerOff"))
    new_callbacks.new_activity((7, "Game"))
    new_callbacks.new_activity((-1, "PowerOff"))
    out = capsys.readouterr().out
    assert "New activity ID 7" in out
    assert "Powering off is starting" in out
    assert "has started" in out
    assert "Powering off completed" in out


async def test_send_command_with_named_device(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    mock_client.get_device_id.return_value = "dev42"
    await cli.send_command(
        mock_client, _make_args(device_id="TV", command="Play", repeat_num=1)
    )
    mock_client.send_commands.assert_awaited()
    assert "Command Sent" in capsys.readouterr().out


async def test_send_command_numeric_known_device(mock_client: MagicMock) -> None:
    mock_client.get_device_name.return_value = "TV"
    await cli.send_command(mock_client, _make_args(device_id="42", command="Play"))
    mock_client.send_commands.assert_awaited()


async def test_send_command_invalid_device(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    mock_client.get_device_id.return_value = None
    mock_client.get_device_name.return_value = None
    await cli.send_command(mock_client, _make_args(device_id="ghost", command="Play"))
    assert "is invalid" in capsys.readouterr().out
    mock_client.send_commands.assert_not_called()


async def test_send_command_repeats_with_delay(mock_client: MagicMock) -> None:
    await cli.send_command(
        mock_client,
        _make_args(device_id="TV", command="Play", repeat_num=3, delay_secs=0.1),
    )
    sent = mock_client.send_commands.call_args.args[0]
    assert len(sent) == 6


async def test_send_command_reports_failures(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    result = MagicMock(code="500", msg="boom")
    result.command = MagicMock(command="Play", device="dev42")
    mock_client.send_commands = AsyncMock(return_value=[result])
    await cli.send_command(mock_client, _make_args(device_id="TV", command="Play"))
    assert "failed with code 500" in capsys.readouterr().out


async def test_send_commands_split(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    await cli.send_commands(
        mock_client, _make_args(device_id="TV", commands="Play Stop  Pause")
    )
    sent = mock_client.send_commands.call_args.args[0]
    assert len(sent) == 3
    assert "Commands Sent" in capsys.readouterr().out


async def test_send_commands_with_delay(mock_client: MagicMock) -> None:
    await cli.send_commands(
        mock_client,
        _make_args(device_id="TV", commands="Play Stop", delay_secs=0.2),
    )
    sent = mock_client.send_commands.call_args.args[0]
    assert len(sent) == 4


async def test_send_commands_invalid_device(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    mock_client.get_device_id.return_value = None
    mock_client.get_device_name.return_value = None
    await cli.send_commands(mock_client, _make_args(device_id="ghost", commands="Play"))
    assert "is invalid" in capsys.readouterr().out


async def test_send_commands_reports_failures(
    mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    result = MagicMock(code="500", msg="bad")
    result.command = MagicMock(command="Play", device="dev42")
    mock_client.send_commands = AsyncMock(return_value=[result])
    await cli.send_commands(mock_client, _make_args(device_id="TV", commands="Play"))
    assert "failed with code 500" in capsys.readouterr().out


async def test_execute_per_hub_executes_provided_func(
    monkeypatch: pytest.MonkeyPatch, mock_client: MagicMock
) -> None:
    monkeypatch.setattr(cli, "get_client", AsyncMock(return_value=mock_client))
    func = AsyncMock()
    args = _make_args(wait=0)
    args.func = func

    await cli.execute_per_hub("10.0.0.5", args)

    func.assert_awaited_once_with(mock_client, args)
    mock_client.close.assert_awaited()


async def test_execute_per_hub_get_client_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "get_client", AsyncMock(return_value=None))
    await cli.execute_per_hub("10.0.0.5", _make_args(wait=0))


async def test_execute_per_hub_get_client_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli, "get_client", AsyncMock(side_effect=harmony_exceptions.TimeOut())
    )
    await cli.execute_per_hub("10.0.0.5", _make_args(wait=0))


async def test_execute_per_hub_func_timeout_swallowed(
    monkeypatch: pytest.MonkeyPatch, mock_client: MagicMock
) -> None:
    monkeypatch.setattr(cli, "get_client", AsyncMock(return_value=mock_client))

    async def boom(_c: object, _a: object) -> None:
        raise harmony_exceptions.TimeOut

    args = _make_args(wait=0)
    args.func = boom
    await cli.execute_per_hub("10.0.0.5", args)
    mock_client.close.assert_awaited()


async def test_execute_per_hub_close_timeout_swallowed(
    monkeypatch: pytest.MonkeyPatch, mock_client: MagicMock
) -> None:
    monkeypatch.setattr(cli, "get_client", AsyncMock(return_value=mock_client))
    mock_client.close = AsyncMock(side_effect=harmony_exceptions.TimeOut())
    await cli.execute_per_hub("10.0.0.5", _make_args(wait=0))


async def test_execute_per_hub_no_func_attr_just_waits(
    monkeypatch: pytest.MonkeyPatch, mock_client: MagicMock
) -> None:
    monkeypatch.setattr(cli, "get_client", AsyncMock(return_value=mock_client))
    await cli.execute_per_hub("10.0.0.5", _make_args(wait=0))
    mock_client.close.assert_awaited()


async def test_run_invalid_wait(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["aioharmony", "--harmony_ip", "10.0.0.5", "--wait", "-5", "show_config"],
    )
    await cli.run()
    assert "Invalid value provided for --wait" in capsys.readouterr().out


async def test_run_discover_branch_returns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["aioharmony", "--discover"])
    await cli.run()


async def test_run_no_func_prints_help(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["aioharmony", "--harmony_ip", "10.0.0.5"])
    await cli.run()
    assert "usage:" in capsys.readouterr().out.lower()


async def test_run_with_logmodules(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, object] = {}

    async def fake_execute(hub: str, args: SimpleNamespace) -> None:
        called["hub"] = hub
        called["wait"] = args.wait

    monkeypatch.setattr(cli, "execute_per_hub", fake_execute)
    monkeypatch.setattr(
        "sys.argv",
        [
            "aioharmony",
            "--harmony_ip",
            "10.0.0.5",
            "--logmodules",
            "aioharmony,other",
            "--loglevel",
            "DEBUG",
            "show_config",
        ],
    )
    await cli.run()
    assert called["hub"] == "10.0.0.5"


async def test_run_dispatches_per_hub(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    async def fake_execute(hub: str, _args: SimpleNamespace) -> None:
        seen.append(hub)

    monkeypatch.setattr(cli, "execute_per_hub", fake_execute)
    monkeypatch.setattr(
        "sys.argv",
        [
            "aioharmony",
            "--harmony_ip",
            "10.0.0.5,10.0.0.6",
            "show_config",
        ],
    )
    await cli.run()
    assert seen == ["10.0.0.5", "10.0.0.6"]


async def test_run_reraises_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    class CustomError(Exception):
        """Local error so the matcher is unambiguous."""

    async def fake_execute(_hub: str, _args: SimpleNamespace) -> None:
        raise CustomError

    monkeypatch.setattr(cli, "execute_per_hub", fake_execute)
    monkeypatch.setattr(
        "sys.argv",
        ["aioharmony", "--harmony_ip", "10.0.0.5", "show_config"],
    )
    with pytest.raises(CustomError):
        await cli.run()


def test_main_runs_and_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    ran: dict[str, bool] = {}

    async def fake_run() -> None:
        ran["yes"] = True

    monkeypatch.setattr(cli, "run", fake_run)
    monkeypatch.setattr(cli, "cancel_tasks", lambda _loop: None)
    cli.main()
    assert ran == {"yes": True}


def test_main_handles_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def boom() -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "run", boom)
    monkeypatch.setattr(cli, "cancel_tasks", lambda _loop: None)
    cli.main()
    out = capsys.readouterr().out
    assert "Exit requested" in out
    assert "Closed" in out


def test_cancel_tasks_cancels_pending() -> None:
    loop = asyncio.new_event_loop()
    try:
        never: asyncio.Future[None] = loop.create_future()

        async def long_running() -> None:
            await never

        task = loop.create_task(long_running())
        with patch.object(cli.asyncio, "sleep", new=AsyncMock(return_value=None)):
            cli.cancel_tasks(loop)
        assert task.cancelled()
    finally:
        loop.close()
