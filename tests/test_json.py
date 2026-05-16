import json as stdlib_json

import pytest

from aioharmony.json import (
    JSONDecodeError,
    json_dumps,
    json_dumps_pretty,
    json_loads,
)


def test_json_dumps():
    assert json_dumps({"foo": "bar"}) == '{"foo":"bar"}'


def test_json_loads():
    assert json_loads('{"foo":"bar"}') == {"foo": "bar"}


def test_json_loads_raises_jsondecodeerror():
    with pytest.raises(JSONDecodeError):
        json_loads("not-json")


def test_jsondecodeerror_is_stdlib_subclass():
    assert issubclass(JSONDecodeError, stdlib_json.JSONDecodeError)


def test_json_dumps_pretty_sorts_keys_and_indents():
    result = json_dumps_pretty({"b": 1, "a": 2})
    assert result == '{\n    "a": 2,\n    "b": 1\n}'


def test_json_dumps_pretty_nested():
    result = json_dumps_pretty({"outer": {"y": 1, "x": 2}})
    assert result == '{\n    "outer": {\n        "x": 2,\n        "y": 1\n    }\n}'
