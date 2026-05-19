"""Tests for the ``aioharmony.__main__`` CLI entry point."""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import aioharmony.__main__ as cli
import aioharmony.exceptions as harmony_exceptions


def _make_args(**overrides):
    """Build an argparse-like Namespace stand-in for tests."""
    base = {
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


@pytest.fixture
def mock_client():
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
    client.sync = AsyncMock(return_value=True)
    client.get_device_id = MagicMock(return_value="dev42")
    client.get_device_name = MagicMock(return_value="TV")
    client.get_activity_id = MagicMock(return_value="9001")
    client.register_handler = MagicMock()
    return client


class TestLoggingFilter:
    """Sync-only tests for the logging filter."""

    def test_exact_match_passes(self):
        rec = logging.LogRecord(
            "aioharmony.harmonyclient", logging.INFO, "f", 1, "m", None, None
        )
        assert cli.LoggingFilter(["aioharmony.harmonyclient"]).filter(rec) is True

    def test_regex_match_passes(self):
        rec = logging.LogRecord("aioharmony.x.y", logging.INFO, "f", 1, "m", None, None)
        assert cli.LoggingFilter(["aioharmony.*"]).filter(rec) is True

    def test_no_match_filtered(self):
        rec = logging.LogRecord("other.module", logging.INFO, "f", 1, "m", None, None)
        assert cli.LoggingFilter(["aioharmony"]).filter(rec) is False


@pytest.mark.asyncio
class TestGetClient:
    async def test_connects_successfully(self, monkeypatch, mock_client, capsys):
        instance = MagicMock(return_value=mock_client)
        monkeypatch.setattr(cli, "HarmonyAPI", instance)

        result = await cli.get_client("10.0.0.5", "WEBSOCKETS", show_responses=True)

        assert result is mock_client
        mock_client.register_handler.assert_called_once()
        out = capsys.readouterr().out
        assert "Trying to connect" in out
        assert "Connected to HUB" in out

    async def test_connect_returns_false(self, monkeypatch, mock_client, capsys):
        mock_client.connect = AsyncMock(return_value=False)
        monkeypatch.setattr(cli, "HarmonyAPI", MagicMock(return_value=mock_client))

        result = await cli.get_client("10.0.0.5", "WEBSOCKETS", show_responses=False)

        assert result is None
        assert "An issue occurred" in capsys.readouterr().out

    async def test_connection_refused(self, monkeypatch, mock_client, capsys):
        mock_client.connect = AsyncMock(side_effect=ConnectionRefusedError())
        monkeypatch.setattr(cli, "HarmonyAPI", MagicMock(return_value=mock_client))

        result = await cli.get_client("10.0.0.5", "WEBSOCKETS", show_responses=False)

        assert result is None
        out = capsys.readouterr().out
        assert "Failed to connect" in out


@pytest.mark.asyncio
class TestSubcommandHandlers:
    async def test_show_config(self, mock_client, capsys):
        await cli.show_config(mock_client, _make_args())
        assert "Living Room" in capsys.readouterr().out

    async def test_show_config_missing(self, mock_client, capsys):
        mock_client.config = None
        await cli.show_config(mock_client, _make_args())
        assert "problem retrieving" in capsys.readouterr().out

    async def test_show_detailed_config(self, mock_client, capsys):
        await cli.show_detailed_config(mock_client, _make_args())
        assert "Living Room" in capsys.readouterr().out

    async def test_show_detailed_config_missing(self, mock_client, capsys):
        mock_client.hub_config = None
        await cli.show_detailed_config(mock_client, _make_args())
        assert "problem retrieving" in capsys.readouterr().out

    async def test_show_current_activity_named(self, mock_client, capsys):
        await cli.show_current_activity(mock_client, _make_args())
        assert "Watch TV" in capsys.readouterr().out

    async def test_show_current_activity_id_only(self, mock_client, capsys):
        mock_client.current_activity = (42, None)
        await cli.show_current_activity(mock_client, _make_args())
        assert "activity_id" in capsys.readouterr().out

    async def test_show_current_activity_missing(self, mock_client, capsys):
        mock_client.current_activity = (None, None)
        await cli.show_current_activity(mock_client, _make_args())
        assert "Unable to retrieve" in capsys.readouterr().out

    async def test_start_activity_no_activity(self, mock_client, capsys):
        await cli.start_activity(mock_client, _make_args(activity=None))
        assert "No activity provided" in capsys.readouterr().out

    async def test_start_activity_numeric_id(self, mock_client, capsys):
        await cli.start_activity(mock_client, _make_args(activity="42"))
        mock_client.start_activity.assert_awaited_with("42")
        assert "Started Activity" in capsys.readouterr().out

    async def test_start_activity_named(self, mock_client, capsys):
        mock_client.get_activity_id.return_value = "9001"
        await cli.start_activity(mock_client, _make_args(activity="Watch TV"))
        mock_client.start_activity.assert_awaited_with("9001")
        assert "Found activity named" in capsys.readouterr().out

    async def test_start_activity_invalid(self, mock_client, capsys):
        mock_client.get_activity_id.return_value = None
        await cli.start_activity(mock_client, _make_args(activity="Nonsense"))
        assert "Invalid activity" in capsys.readouterr().out

    async def test_start_activity_failed(self, mock_client, capsys):
        mock_client.start_activity = AsyncMock(return_value=(False, "boom"))
        await cli.start_activity(mock_client, _make_args(activity="42"))
        assert "Activity start failed" in capsys.readouterr().out

    async def test_start_activity_power_off_id(self, mock_client):
        await cli.start_activity(mock_client, _make_args(activity="-1"))
        mock_client.start_activity.assert_awaited_with("-1")

    async def test_power_off_ok(self, mock_client, capsys):
        await cli.power_off(mock_client, _make_args())
        assert "Powered Off" in capsys.readouterr().out

    async def test_power_off_failed(self, mock_client, capsys):
        mock_client.power_off = AsyncMock(return_value=False)
        await cli.power_off(mock_client, _make_args())
        assert "Power off failed" in capsys.readouterr().out

    async def test_change_channel_ok(self, mock_client, capsys):
        await cli.change_channel(mock_client, _make_args(channel="7"))
        mock_client.change_channel.assert_awaited_with("7")
        assert "Changed to channel 7" in capsys.readouterr().out

    async def test_change_channel_failed(self, mock_client, capsys):
        mock_client.change_channel = AsyncMock(return_value=False)
        await cli.change_channel(mock_client, _make_args(channel="7"))
        assert "Change to channel 7 failed" in capsys.readouterr().out

    async def test_sync_ok(self, mock_client, capsys):
        await cli.sync(mock_client, _make_args())
        assert "Sync complete" in capsys.readouterr().out

    async def test_sync_failed(self, mock_client, capsys):
        mock_client.sync = AsyncMock(return_value=False)
        await cli.sync(mock_client, _make_args())
        assert "Sync failed" in capsys.readouterr().out

    async def test_just_listen_registers_handler(self, mock_client, capsys):
        await cli.just_listen(mock_client, _make_args(show_responses=False))
        mock_client.register_handler.assert_called_once()
        assert "Starting to listen" in capsys.readouterr().out

    async def test_just_listen_skips_when_already_showing(self, mock_client):
        await cli.just_listen(mock_client, _make_args(show_responses=True))
        mock_client.register_handler.assert_not_called()

    async def test_just_listen_callback_prints_message(self, mock_client, capsys):
        await cli.just_listen(mock_client, _make_args(show_responses=False))
        handler = mock_client.register_handler.call_args.kwargs["handler"]
        capsys.readouterr()
        handler.handler_obj("hello-world")
        assert "hello-world" in capsys.readouterr().out

    async def test_listen_for_new_activities_starting(self, mock_client, capsys):
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


@pytest.mark.asyncio
class TestSendCommand:
    async def test_send_command_with_named_device(self, mock_client, capsys):
        mock_client.get_device_id.return_value = "dev42"
        await cli.send_command(
            mock_client, _make_args(device_id="TV", command="Play", repeat_num=1)
        )
        mock_client.send_commands.assert_awaited()
        assert "Command Sent" in capsys.readouterr().out

    async def test_send_command_numeric_known_device(self, mock_client):
        mock_client.get_device_name.return_value = "TV"
        await cli.send_command(mock_client, _make_args(device_id="42", command="Play"))
        mock_client.send_commands.assert_awaited()

    async def test_send_command_invalid_device(self, mock_client, capsys):
        mock_client.get_device_id.return_value = None
        mock_client.get_device_name.return_value = None
        await cli.send_command(
            mock_client, _make_args(device_id="ghost", command="Play")
        )
        assert "is invalid" in capsys.readouterr().out
        mock_client.send_commands.assert_not_called()

    async def test_send_command_repeats_with_delay(self, mock_client):
        await cli.send_command(
            mock_client,
            _make_args(device_id="TV", command="Play", repeat_num=3, delay_secs=0.1),
        )
        sent = mock_client.send_commands.call_args.args[0]
        assert len(sent) == 6

    async def test_send_command_reports_failures(self, mock_client, capsys):
        result = MagicMock(code="500", msg="boom")
        result.command = MagicMock(command="Play", device="dev42")
        mock_client.send_commands = AsyncMock(return_value=[result])
        await cli.send_command(mock_client, _make_args(device_id="TV", command="Play"))
        assert "failed with code 500" in capsys.readouterr().out


@pytest.mark.asyncio
class TestSendCommands:
    async def test_send_commands_split(self, mock_client, capsys):
        await cli.send_commands(
            mock_client, _make_args(device_id="TV", commands="Play Stop  Pause")
        )
        sent = mock_client.send_commands.call_args.args[0]
        assert len(sent) == 3
        assert "Commands Sent" in capsys.readouterr().out

    async def test_send_commands_with_delay(self, mock_client):
        await cli.send_commands(
            mock_client,
            _make_args(device_id="TV", commands="Play Stop", delay_secs=0.2),
        )
        sent = mock_client.send_commands.call_args.args[0]
        assert len(sent) == 4

    async def test_send_commands_invalid_device(self, mock_client, capsys):
        mock_client.get_device_id.return_value = None
        mock_client.get_device_name.return_value = None
        await cli.send_commands(
            mock_client, _make_args(device_id="ghost", commands="Play")
        )
        assert "is invalid" in capsys.readouterr().out

    async def test_send_commands_reports_failures(self, mock_client, capsys):
        result = MagicMock(code="500", msg="bad")
        result.command = MagicMock(command="Play", device="dev42")
        mock_client.send_commands = AsyncMock(return_value=[result])
        await cli.send_commands(
            mock_client, _make_args(device_id="TV", commands="Play")
        )
        assert "failed with code 500" in capsys.readouterr().out


@pytest.mark.asyncio
class TestExecutePerHub:
    async def test_executes_provided_func(self, monkeypatch, mock_client):
        monkeypatch.setattr(cli, "get_client", AsyncMock(return_value=mock_client))
        func = AsyncMock()
        args = _make_args(wait=0)
        args.func = func

        await cli.execute_per_hub("10.0.0.5", args)

        func.assert_awaited_once_with(mock_client, args)
        mock_client.close.assert_awaited()

    async def test_get_client_returns_none(self, monkeypatch):
        monkeypatch.setattr(cli, "get_client", AsyncMock(return_value=None))
        await cli.execute_per_hub("10.0.0.5", _make_args(wait=0))

    async def test_get_client_timeout(self, monkeypatch):
        monkeypatch.setattr(
            cli, "get_client", AsyncMock(side_effect=harmony_exceptions.TimeOut())
        )
        await cli.execute_per_hub("10.0.0.5", _make_args(wait=0))

    async def test_func_timeout_swallowed(self, monkeypatch, mock_client):
        monkeypatch.setattr(cli, "get_client", AsyncMock(return_value=mock_client))

        async def boom(_c, _a):
            raise harmony_exceptions.TimeOut

        args = _make_args(wait=0)
        args.func = boom
        await cli.execute_per_hub("10.0.0.5", args)
        mock_client.close.assert_awaited()

    async def test_close_timeout_swallowed(self, monkeypatch, mock_client):
        monkeypatch.setattr(cli, "get_client", AsyncMock(return_value=mock_client))
        mock_client.close = AsyncMock(side_effect=harmony_exceptions.TimeOut())
        await cli.execute_per_hub("10.0.0.5", _make_args(wait=0))

    async def test_no_func_attr_just_waits(self, monkeypatch, mock_client):
        monkeypatch.setattr(cli, "get_client", AsyncMock(return_value=mock_client))
        await cli.execute_per_hub("10.0.0.5", _make_args(wait=0))
        mock_client.close.assert_awaited()


@pytest.mark.asyncio
class TestRunArgparse:
    async def test_run_invalid_wait(self, monkeypatch, capsys):
        monkeypatch.setattr(
            "sys.argv",
            ["aioharmony", "--harmony_ip", "10.0.0.5", "--wait", "-5", "show_config"],
        )
        await cli.run()
        assert "Invalid value provided for --wait" in capsys.readouterr().out

    async def test_run_discover_branch_returns(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["aioharmony", "--discover"])
        await cli.run()

    async def test_run_no_func_prints_help(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["aioharmony", "--harmony_ip", "10.0.0.5"])
        await cli.run()
        assert "usage:" in capsys.readouterr().out.lower()

    async def test_run_with_logmodules(self, monkeypatch):
        called = {}

        async def fake_execute(hub, args):
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
        try:
            await cli.run()
        finally:
            for h in list(logging.getLogger().handlers):
                logging.getLogger().removeHandler(h)
        assert called["hub"] == "10.0.0.5"

    async def test_run_dispatches_per_hub(self, monkeypatch):
        seen = []

        async def fake_execute(hub, _args):
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
        try:
            await cli.run()
        finally:
            for h in list(logging.getLogger().handlers):
                logging.getLogger().removeHandler(h)
        assert seen == ["10.0.0.5", "10.0.0.6"]

    async def test_run_reraises_exception(self, monkeypatch):
        class CustomError(Exception):
            """Local error so the matcher is unambiguous."""

        async def fake_execute(_hub, _args):
            raise CustomError

        monkeypatch.setattr(cli, "execute_per_hub", fake_execute)
        monkeypatch.setattr(
            "sys.argv",
            ["aioharmony", "--harmony_ip", "10.0.0.5", "show_config"],
        )
        try:
            with pytest.raises(CustomError):
                await cli.run()
        finally:
            for h in list(logging.getLogger().handlers):
                logging.getLogger().removeHandler(h)


class TestMainEntry:
    def test_main_runs_and_closes(self, monkeypatch):
        ran = {}

        async def fake_run():
            ran["yes"] = True

        monkeypatch.setattr(cli, "run", fake_run)
        monkeypatch.setattr(cli, "cancel_tasks", lambda _loop: None)
        cli.main()
        assert ran == {"yes": True}

    def test_main_handles_keyboard_interrupt(self, monkeypatch, capsys):
        async def boom():
            raise KeyboardInterrupt

        monkeypatch.setattr(cli, "run", boom)
        monkeypatch.setattr(cli, "cancel_tasks", lambda _loop: None)
        cli.main()
        out = capsys.readouterr().out
        assert "Exit requested" in out
        assert "Closed" in out

    def test_cancel_tasks_cancels_pending(self):
        loop = asyncio.new_event_loop()
        try:

            async def long_running():
                await asyncio.sleep(60)

            task = loop.create_task(long_running())
            with patch.object(cli.asyncio, "sleep", new=AsyncMock(return_value=None)):
                cli.cancel_tasks(loop)
            assert task.cancelled() or task.done()
        finally:
            loop.close()
