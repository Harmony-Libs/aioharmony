"""Start a named activity on a Harmony Hub."""

from __future__ import annotations

import argparse
import asyncio
import sys

from aioharmony.harmonyapi import HarmonyAPI


async def start_activity(ip_address: str, protocol: str, activity_name: str) -> int:
    client = HarmonyAPI(ip_address=ip_address, protocol=protocol)
    await client.connect()
    try:
        activity_id = client.get_activity_id(activity_name)
        if activity_id is None:
            print(f"Activity {activity_name!r} is not configured on {client.name}")
            return 2

        success, message = await client.start_activity(activity_id)
        if not success:
            print(f"Failed to start {activity_name!r}: {message}")
            return 1

        print(f"Started {activity_name!r} on {client.name}")
        return 0
    finally:
        await client.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ip_address", help="Harmony Hub IP address")
    parser.add_argument("activity", help="Activity name as it appears in MyHarmony")
    parser.add_argument(
        "--protocol",
        choices=("WEBSOCKETS", "XMPP"),
        default="WEBSOCKETS",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    sys.exit(asyncio.run(start_activity(args.ip_address, args.protocol, args.activity)))
