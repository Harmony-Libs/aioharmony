"""Constants used throughout the modules."""

import asyncio
from collections.abc import Callable
from typing import Any, Literal, NamedTuple

#
# DEFAULT values
#
DEFAULT_CMD = "vnd.logitech.connect"
DEFAULT_DISCOVER_STRING = "_logitech-reverse-bonjour._tcp.local."
DEFAULT_XMPP_HUB_PORT = "5222"
DEFAULT_WS_HUB_PORT = "8088"
DEFAULT_HARMONY_MIME = "vnd.logitech.harmony/vnd.logitech.harmony.engine"

WEBSOCKETS = "WEBSOCKETS"
XMPP = "XMPP"

PROTOCOL = Literal["WEBSOCKETS", "XMPP"]

#
# The HUB commands that can be send
#
HUB_COMMANDS = {
    "change_channel": {"mime": "harmony.engine", "command": "changeChannel"},
    "get_current_state": {
        "mime": "vnd.logitech.connect/vnd.logitech.statedigest",
        "command": "get",
    },
    "get_config": {"mime": DEFAULT_HARMONY_MIME, "command": "config"},
    "get_current_activity": {
        "mime": DEFAULT_HARMONY_MIME,
        "command": "getCurrentActivity",
    },
    "send_command": {"mime": DEFAULT_HARMONY_MIME, "command": "holdAction"},
    "start_activity": {"mime": "harmony.activityengine", "command": "runactivity"},
    "sync": {"mime": "setup.sync", "command": None},
    "provision_info": {"mime": "setup.account", "command": "getProvisionInfo"},
    "discovery": {"mime": "connect.discoveryinfo", "command": "get"},
}

#
# Different types used within aioharmony
#

# Type for callback parameters. A plain callable callback receives a single
# positional argument: the result/message. See helpers.call_raw_callback.
CallbackType = asyncio.Future[Any] | asyncio.Event | Callable[[object], Any]


class ClientCallbackType(NamedTuple):
    connect: CallbackType | None
    disconnect: CallbackType | None
    new_activity_starting: CallbackType | None
    new_activity: CallbackType | None
    config_updated: CallbackType | None


class ConnectorCallbackType(NamedTuple):
    connect: CallbackType | None
    disconnect: CallbackType | None


class ClientConfigType(NamedTuple):
    config: dict[str, Any]
    info: dict[str, Any]
    discover_info: dict[str, Any]
    hub_state: dict[str, Any]
    config_version: int | None
    activities: list[dict[str, Any]]
    devices: list[dict[str, Any]]


# Type for a command to send to the HUB
class SendCommandDevice(NamedTuple):
    device: int
    command: str
    delay: float


# Type for send command to aioharmony,
SendCommand = SendCommandDevice | float | int
SendCommandArg = SendCommand | list[SendCommand]


# Response from send commands.
class SendCommandResponse(NamedTuple):
    command: SendCommandDevice
    code: str
    msg: str
