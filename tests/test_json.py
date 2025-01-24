from aioharmony.json import json_dumps, json_loads


def test_json_dumps():
    assert json_dumps({"foo": "bar"}) == '{"foo":"bar"}'


def test_json_loads():
    assert json_loads('{"foo":"bar"}') == {"foo": "bar"}
