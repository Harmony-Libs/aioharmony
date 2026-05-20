# aioharmony examples

Runnable examples for the Python API. Each script is self-contained
and takes the Hub IP as the first positional argument:

```bash
python examples/start_activity.py 192.168.1.203 "Watch TV"
python examples/show_current_activity.py 192.168.1.203
python examples/power_off.py 192.168.1.203
python examples/send_command.py 192.168.1.203 "Living Room TV" VolumeUp
python examples/listen_activity_changes.py 192.168.1.203
```

The scripts default to the `WEBSOCKETS` protocol. Pass `--protocol XMPP`
if your hub still has XMPP enabled (legacy firmware on port 5222).
