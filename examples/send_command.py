"""Send a single IR command to one of the hub's configured devices."""

from __future__ import annotations

import argparse
import asyncio
import sys

from aioharmony.const import SendCommandDevice
from aioharmony.harmonyapi import HarmonyAPI


async def send_command(
    ip_address: str,
    protocol: str,
    device_name: str,
    command: str,
    hold_secs: float,
) -> int:
    client = HarmonyAPI(ip_address=ip_address, protocol=protocol)
    await client.connect()
    try:
        device_id = client.get_device_id(device_name)
        if device_id is None:
            print(f"Device {device_name!r} not found on {client.name}")
            return 2

        snd = SendCommandDevice(device=device_id, command=command, delay=hold_secs)
        errors = await client.send_commands(snd)
        if errors:
            for err in errors:
                print(f"{err.command.command} failed: {err.msg} (code {err.code})")
            return 1
        print(f"{client.name}: sent {command!r} to {device_name!r}")
        return 0
    finally:
        await client.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ip_address", help="Harmony Hub IP address")
    parser.add_argument("device", help="Device name as it appears in MyHarmony")
    parser.add_argument("command", help="Command name, e.g. 'VolumeUp' or 'PowerOn'")
    parser.add_argument(
        "--protocol",
        choices=("WEBSOCKETS", "XMPP"),
        default="WEBSOCKETS",
    )
    parser.add_argument(
        "--hold-secs",
        type=float,
        default=0.2,
        help="How long to hold the button down (default: 0.2s)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    sys.exit(
        asyncio.run(
            send_command(
                args.ip_address,
                args.protocol,
                args.device,
                args.command,
                args.hold_secs,
            )
        )
    )
