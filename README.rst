aioharmony
==========

.. image:: https://codecov.io/gh/Harmony-Libs/aioharmony/branch/main/graph/badge.svg
   :target: https://codecov.io/gh/Harmony-Libs/aioharmony
   :alt: Codecov

Python library for programmatically using a Logitech Harmony Link or Ultimate Hub.

This library originated from `iandday/pyharmony <https://github.com/iandday/pyharmony>`__ which was a fork
of `bkanuka/pyharmony <https://github.com/bkanuka/pyharmony>`__ with the intent to:

- Make the harmony library asyncio
- Ability to provide one's own custom callbacks to be called
- Automatic reconnect, even if re-connection cannot be established for a time
- More easily get the HUB configuration through API call
- Additional callbacks: connect, disconnect, HUB configuration updated
- Using unique msgid's ensuring that responses from the HUB are correctly managed.

Protocol
--------

As the harmony protocol is being worked out, notes will be in PROTOCOL.md.

Status
------

* Retrieving current activity
* Querying for entire device information
* Querying for activity information only
* Querying for current activity
* Starting Activity
* Sending Command
* Changing channels
* Custom callbacks.

Installation
------------

.. code:: bash

    pip install aioharmony

Python API usage
----------------

``aioharmony`` is an ``asyncio`` library, so every method that talks to the
Hub is a coroutine and must be ``await``-ed from inside an event loop.
The public entry point is the ``HarmonyAPI`` class.

Connecting to a Hub
~~~~~~~~~~~~~~~~~~~

.. code:: python

    import asyncio

    from aioharmony.harmonyapi import HarmonyAPI


    async def main() -> None:
        client = HarmonyAPI(ip_address="192.168.1.203", protocol="WEBSOCKETS")
        await client.connect()
        try:
            print(f"Connected to {client.name} (firmware {client.fw_version})")
        finally:
            await client.close()


    asyncio.run(main())

``protocol`` accepts ``"WEBSOCKETS"`` (default for modern firmware) or
``"XMPP"`` (legacy hubs that still have XMPP enabled). Always pair
``connect()`` with ``close()`` — typically inside a ``try``/``finally`` —
so the background reconnect loop and the WebSocket session shut down
cleanly.

Starting an activity
~~~~~~~~~~~~~~~~~~~~

``start_activity()`` takes an activity ID, not a name. Use
``get_activity_id()`` to look the ID up:

.. code:: python

    async def start_watch_tv(client: HarmonyAPI) -> None:
        activity_id = client.get_activity_id("Watch TV")
        if activity_id is None:
            raise ValueError("Activity 'Watch TV' is not configured on this hub")
        success, message = await client.start_activity(activity_id)
        if not success:
            raise RuntimeError(f"Failed to start activity: {message}")

Showing the current activity / powering off
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: python

    async def show_and_power_off(client: HarmonyAPI) -> None:
        activity_id, activity_name = client.current_activity
        print(f"Current activity: {activity_name} ({activity_id})")
        await client.power_off()

Sending a device command
~~~~~~~~~~~~~~~~~~~~~~~~

``send_commands()`` takes a ``SendCommandDevice`` (or a list of them,
optionally interleaved with ``float`` delays in seconds). ``device`` is
the device ID — look it up with ``get_device_id()``:

.. code:: python

    from aioharmony.const import SendCommandDevice


    async def volume_up(client: HarmonyAPI, device_name: str) -> None:
        device_id = client.get_device_id(device_name)
        if device_id is None:
            raise ValueError(f"Device {device_name!r} not found")
        command = SendCommandDevice(device=device_id, command="VolumeUp", delay=0.2)
        # send_commands returns an empty list on success, or a list of
        # SendCommandResponse entries describing the failures.
        errors = await client.send_commands(command)
        for err in errors:
            print(f"{err.command.command} failed: {err.msg} (code {err.code})")

Reacting to hub events with callbacks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``ClientCallbackType`` is a ``NamedTuple`` with five slots
(``connect``, ``disconnect``, ``new_activity_starting``,
``new_activity``, ``config_updated``). Each slot accepts a plain
callable, an ``asyncio.Future``, an ``asyncio.Event``, or ``None``:

.. code:: python

    from aioharmony.const import ClientCallbackType


    def on_new_activity(info: tuple[int, str]) -> None:
        activity_id, activity_name = info
        print(f"Now running: {activity_name} ({activity_id})")


    callbacks = ClientCallbackType(
        connect=None,
        disconnect=None,
        new_activity_starting=None,
        new_activity=on_new_activity,
        config_updated=None,
    )
    client = HarmonyAPI(
        ip_address="192.168.1.203", protocol="WEBSOCKETS", callbacks=callbacks
    )

See the ``examples/`` directory in the source tree for runnable
versions of each snippet above.

Command-line usage
------------------

.. code:: bash

    usage: __main__.py [-h] (--harmony_ip HARMONY_IP | --discover)
                       [--protocol {WEBSOCKETS,XMPP}]
                       [--loglevel {DEBUG,INFO,WARNING,ERROR,CRITICAL}]
                       [--logmodules LOGMODULES]
                       [--show_responses | --no-show_responses] [--wait WAIT]
                       {show_config,show_detailed_config,show_current_activity,start_activity,power_off,sync,listen,activity_monitor,send_command,change_channel}
                       ...

    aioharmony - Harmony device control

    positional arguments:
      {show_config,show_detailed_config,show_current_activity,start_activity,power_off,sync,listen,activity_monitor,send_command,change_channel}
        show_config         Print the Harmony device configuration.
        show_detailed_config
                            Print the detailed Harmony device configuration.
        show_current_activity
                            Print the current activity config.
        start_activity      Switch to a different activity.
        power_off           Stop the activity.
        sync                Sync the harmony.
        listen              Output everything HUB sends out. Use in combination
                            with --wait.
        activity_monitor    Monitor and show when an activity is changing. Use in
                            combination with --wait to keep monitoring
                            foractivities otherwise only current activity will be
                            shown.
        send_command        Send a simple command.
        send_commands       Send a series of simple commands separated by spaces.
        change_channel      Change the channel

    optional arguments:
      -h, --help            show this help message and exit
      --harmony_ip HARMONY_IP
                            IP Address of the Harmony device, multiple IPs can be
                            specified as a comma separated list without spaces.
                            (default: None)
      --discover            Scan for Harmony devices. (default: False)
      --protocol {WEBSOCKETS,XMPP}
                            Protocol to use to connect to HUB. Note for XMPP one
                            has to ensure that XMPP is enabledon the hub.
                            (default: None)
      --loglevel {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                            Logging level for all components to print to the
                            console. (default: ERROR)
      --logmodules LOGMODULES
                            Restrict logging to modules specified. Multiple can be
                            provided as a comma separated list without any spaces.
                            Use * to include any further submodules. (default:
                            None)
      --show_responses      Print out responses coming from HUB. (default: False)
      --no-show_responses   Do not print responses coming from HUB. (default:
                            False)
      --wait WAIT           How long to wait in seconds after completion, useful
                            in combination with --show-responses. Use -1 to wait
                            infinite, otherwise has to be a positive number.
                            (default: 0)


Release Notes
-------------

See `changelog <https://github.com/Harmony-Libs/aioharmony/blob/main/CHANGELOG.md>` for release notes

TODO
----

* Redo discovery for asyncio. This will be done once XMPP is re-implemented by Logitech
* More items can be done from the Harmony iOS app; determining what could be done within the library as well
* Is it possible to update device configuration?
