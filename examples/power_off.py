"""Power off the currently running activity (no-op if hub is already off)."""

from __future__ import annotations

import argparse
import asyncio
import sys

from aioharmony.harmonyapi import HarmonyAPI


async def power_off(ip_address: str, protocol: str) -> int:
    client = HarmonyAPI(ip_address=ip_address, protocol=protocol)
    await client.connect()
    try:
        if await client.power_off():
            print(f"{client.name}: powered off")
            return 0
        print(f"{client.name}: power off failed")
        return 1
    finally:
        await client.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ip_address", help="Harmony Hub IP address")
    parser.add_argument(
        "--protocol",
        choices=("WEBSOCKETS", "XMPP"),
        default="WEBSOCKETS",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    sys.exit(asyncio.run(power_off(args.ip_address, args.protocol)))
