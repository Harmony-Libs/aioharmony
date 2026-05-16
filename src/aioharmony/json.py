import json as _stdlib_json
from functools import partial
from typing import Any

JSONDecodeError = _stdlib_json.JSONDecodeError

try:
    import orjson

    json_loads = orjson.loads

    def json_dumps(obj: Any) -> str:
        return orjson.dumps(obj).decode()

except ImportError:
    json_dumps = partial(_stdlib_json.dumps, separators=(",", ":"))
    json_loads = _stdlib_json.loads


def json_dumps_pretty(obj: Any) -> str:
    """Human-readable JSON dump with stable key ordering."""
    return _stdlib_json.dumps(obj, sort_keys=True, indent=4, separators=(",", ": "))
