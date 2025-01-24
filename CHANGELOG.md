# CHANGELOG


## v0.2.11 (2025-01-24)

### Bug Fixes

- Ensure strong references are held to tasks
  ([#50](https://github.com/Harmony-Libs/aioharmony/pull/50),
  [`36f1f28`](https://github.com/Harmony-Libs/aioharmony/commit/36f1f289431ad3efc26cb9611a091b3b8fbedac5))

## v0.2.10 (2023-03-16)

- Fixed: Fixed "module asyncio has no attribute coroutine" exception in call_raw_callback function on Python 3.11
- Changed: Bumped minimum required Python version to 3.9

## v0.2.9 (2022-01-10)

- Fixed: Fixed exception in Python 3.10 by removing loop parameter (swolix)

## v0.2.8 (2021-10-17)

- Changed: Get remote_id from Hub without creating websocket connection
  
## v0.2.7 (2021-02-05)

- Fixed: Registered handlers would not be unregistered after a timeout when sending commands to HUB.
- Updated slixmpp from >= 1.5.2 to >= 1.7.0
- Updated aiohttp from >= 3.4  to 3.7.3

## v0.2.6 (2020-07-29)

- Changed: If XMPP not enabled and no protocol provided then message will be DEBUG instead of Warning to enable XMPP.
- Fixed: If connect using XMPP fails with for example Connection Refused then it will be logged now and connection marked as failed for reconnection.

## v0.2.5 (2020-06-19)

- Fixed: When using XMPP protocol the switching of an activity was not always discovered.
- Fixed: Call to stop handlers will now be called when timeout occurs on disconnect
- Changed: ClientCallbackType is now in aioharmony.const instead of aioharmony.harmonyclient.
- Changed: default log level for aioharmony main is now ERROR
- New: callback option new_activity_starting to allow a callback when a new activity is being started (new_activity is called when switching activity is completed)
- New: 3 new HANDLER types have been added:
    - HANDLER_START_ACTIVITY_NOTIFY_STARTED: activity is being started
    - HANDLER_STOP_ACTIVITY_NOTIFY_STARTED: power off is started
    - HANDLER_START_ACTIVITY_NOTIRY_INPROGRESS: activity switch is in progress
- New: Protocol to use can be specified (WEBSOCKETS or XMPP) to force specific protocol to be used. If not provided XMPP will be used unless not available then WEBSOCKETS will be used.
- New: protocol used to connect can now be retrieved. It will return WEBSOCKETS when connected over web sockets or XMPP.
- New: One can now supply multiple IP addresses for Harmony HUBs when using aioharmony main.
- New: option activity_monitor for aioharmony main to allow just monitoring of activity changes
- New: option logmodules for aioharmony main to specify the modules to put logging information for

## v0.2.4 (2020-06-08)

- Friendly Name of Harmony HUB was not retrieved anymore, this is now available again
- Remote ID was not retrieved anymore, this is now available again
- If HUB disconnects when retrieving information then retrieval will be retried.
- Executing aioharmony with option show_detailed_config will now show all config retrieved from HUB

## v0.2.3 (2020-06-05)

- Updated requirement for slixmpp to 1.5.2 as that version works with Home Assistant

## v0.2.2 (Unknown)

- Added closing code from aiohttp for web sockets in debug logging if closing code provided.
- Fixed further potential issue where on some OS's sockets would not be closed by now force closing them (merge from 0.1.13)
- Fixed listen parameter as it would just exit instead of continuously wait.

## v0.2.1 (2019-09-03)

- Fixed issue in sending commands to HUB wbe using XMPP protocol.

## v0.2.0 (Unknown)

- Support for XMPP. If XMPP is enabled on Hub then that will be used, otherwise fallback to web sockets.
  There are no changes to the API for this. XMPP has to be explicitly enabled on the Harmony HUB.
  To do so open the Harmony app and go to: Menu > Harmony Setup > Add/Edit Devices & Activities > Remote & Hub > Enable XMPP
  Same steps can be followed to disable XMPP again.
- Log entries from responsehandler class will now include ip address of HUB for easier identification

## v0.1.13 (Unknown)

- Fixed further potential issue where on some OS's sockets would not be closed by now force closing them.

## v0.1.12 (Unknown)

- Fixed issue where connection debug messages would not be shown on failed reconnects.
- Added debug log entry when connected to HUB.

## v0.1.11 (Unknown)

- Timeout changed from 30 seconds to 5 seconds for network activity.
- For reconnect, first wait for 1 second before starting reconnects.

## v0.1.10 (Unknown)

- On reconnect the wait time will now start at 1 seconds and double every time with a maximum of 30 seconds.
- Reconnect sometimes might not work if request to close was received over web socket but it never was closed.

## v0.1.9 (Unknown)

- Fixed "Network unreachable" or "Host unreachable" on certain installations (i.e. in Docker, HassIO)

## v0.1.8 (Unknown)

NOTE: This version will ONLY work with 4.15.250 or potentially higher. It will not work with lower versions!

- Fix traceback if HUB info is not received.
- Fix for new HUB version 4.15.250. (Thanks to `reneboer <https://github.com/reneboer>`__ for providing the quick fix).

## v0.1.7 (Unknown)

- Fix traceback if no configuration retrieved or items missing from configuration (i.e. no activities)
- Retrieve current activity only after retrieving configuration

## v0.1.6 (Unknown)

- Ignore response code 200 when for sending commands
- Upon reconnect, errors will be logged on 1st try only, any subsequent retry until connection is successful will
  only provide DEBUG log entries.

## v0.1.5 (Unknown)

- Exception when an invalid command was sent to HUB (or sending command failed on HUB).
- Messages for failed commands were not printed in main.

## v0.1.4 (Unknown)

- Exception when retrieve_hub_info failed to retrieve information
- call_callback helper would never return True on success.
- Retry connect on reconnect (was not awaited upon)

## v0.1.3 (2019-01-01)

- Retry connect on reconnect

## v0.1.2 (2018-12-30)

- Enable callback connect only once initial connect and initialization is completed.
- Fix exception when activity/device name/id is None when trying to retrieve name/id.
- Fixed content type and name of README in setup.py

## v0.1.1 (2018-12-29)

- No significant changes

## v0.1.0 (2018-12-28)

- Initial Release