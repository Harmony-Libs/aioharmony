from functools import partial
from typing import Any

try:
    import orjson

    json_loads = orjson.loads

    def json_dumps(obj: Any) -> str:
        return orjson.dumps(obj).decode()

except ImportError:
    import json

    json_dumps = partial(json.dumps, separators=(",", ":"))
    json_loads = json.loads
