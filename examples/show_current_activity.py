"""Print the currently running activity on a Harmony Hub."""

from __future__ import annotations

import argparse
import asyncio

from aioharmony.harmonyapi import HarmonyAPI


async def show_current_activity(ip_address: str, protocol: str) -> None:
    client = HarmonyAPI(ip_address=ip_address, protocol=protocol)
    await client.connect()
    try:
        activity_id, activity_name = client.current_activity
        print(f"{client.name}: {activity_name} ({activity_id})")
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
    asyncio.run(show_current_activity(args.ip_address, args.protocol))
