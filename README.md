aioharmony
=======

Python library for programmatically using a Logitech Harmony Link or Ultimate Hub.

This library originated from [iandday/pyharmony](https://github.com/iandday/pyharmony) which was a fork 
of [bkanuka/pyharmony](https://github.com/bkanuka/pyharmony) with the intent to:

- Make the harmony library asyncio
- Ability to provide one's own custom callbacks to be called
- Automatic reconnect, even if re-connection cannot be established for a time
- More easily get the HUB configuration through API call
- Additional callbacks: connect, disconnect, HUB configuration updated
- Using unique msgid's ensuring that responses from the HUB are correctly managed. 

Protocol
--------

As the harmony protocol is being worked out, notes will be in PROTOCOL.md. Currently it is using web sockets 
due to a change by Logitech. Logitech has informed they will re-open XMPP sometime in January/2019. Once re-opened
this library will be moved to use XMPP. 

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

Usage
-----

aioharmony - Harmony device control

```
usage: aioharmony [-h] (--harmony_ip HARMONY_IP | --discover)
                  [--harmony_port HARMONY_PORT]
                  [--loglevel {DEBUG,INFO,WARNING,ERROR,CRITICAL}]
                  [--show_responses | --no-show_responses] [--wait WAIT]
                  {show_config,show_detailed_config,show_current_activity,start_activity,power_off,sync,listen,send_command,change_channel}
                  ...

aioharmony - Harmony device control

positional arguments:
  {show_config,show_detailed_config,show_current_activity,start_activity,power_off,sync,listen,send_command,change_channel}
    show_config         Print the Harmony device configuration.
    show_detailed_config
                        Print the detailed Harmony device configuration.
    show_current_activity
                        Print the current activity config.
    start_activity      Switch to a different activity.
    power_off           Stop the activity.
    sync                Sync the harmony.
    listen              Output everything HUB sends out
    send_command        Send a simple command.
    change_channel      Change the channel

optional arguments:
  -h, --help            show this help message and exit
  --harmony_ip HARMONY_IP
                        IP Address of the Harmony device. (default: None)
  --discover            Scan for Harmony devices. (default: False)
  --harmony_port HARMONY_PORT
                        Network port that the Harmony is listening on.
                        (default: 5222)
  --loglevel {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        Logging level for all components to print to the
                        console. (default: INFO)
  --show_responses      Print out responses coming from HUB. (default: False)
  --no-show_responses   Do not print responses coming from HUB. (default:
                        False)
  --wait WAIT           How long to wait in seconds after completion, useful
                        in combination with --show-responses. Use -1 to wait
                        infinite, otherwise has to be a positive number.
                        (default: 0)

```

TODO
----

* Redo discovery for asyncio. This will be done once XMPP is re-implemented by Logitech
* More items can be done from the Harmony iOS app; determining what could be done within the library as well
* Is it possible to update device configuration?
