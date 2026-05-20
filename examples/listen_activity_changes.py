"""Watch a Harmony Hub and print activity transitions as they happen.

Demonstrates how to install a ``ClientCallbackType`` so user code is
notified when the hub starts a new activity or finishes switching.
Press Ctrl-C to exit.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
from datetime import datetime

from aioharmony.const import ClientCallbackType
from aioharmony.harmonyapi import HarmonyAPI


def _stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _on_new_activity_starting(info: tuple[int, str]) -> None:
    activity_id, activity_name = info
    print(f"{_stamp()} starting: {activity_name} ({activity_id})")


def _on_new_activity(info: tuple[int, str]) -> None:
    activity_id, activity_name = info
    print(f"{_stamp()} running:  {activity_name} ({activity_id})")


async def listen(ip_address: str, protocol: str) -> None:
    callbacks = ClientCallbackType(
        connect=None,
        disconnect=None,
        new_activity_starting=_on_new_activity_starting,
        new_activity=_on_new_activity,
        config_updated=None,
    )
    client = HarmonyAPI(ip_address=ip_address, protocol=protocol, callbacks=callbacks)
    await client.connect()
    try:
        activity_id, activity_name = client.current_activity
        print(f"{_stamp()} current:  {activity_name} ({activity_id})")
        print("Listening for activity changes. Press Ctrl-C to exit.")
        await asyncio.Event().wait()
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
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(listen(args.ip_address, args.protocol))
