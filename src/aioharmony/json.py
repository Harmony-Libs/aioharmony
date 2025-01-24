from typing import Any

import orjson

try:
    import orjson

    json_loads = orjson.loads

    def json_dumps(obj: Any) -> str:
        return orjson.dumps(obj).decode()

except ImportError:
    import json

    json_dumps = json.dumps
    json_loads = json.loads
