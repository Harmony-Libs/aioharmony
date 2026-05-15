"""Tests for ``aioharmony.helpers``."""

import asyncio
import logging

import pytest

from aioharmony.helpers import call_callback, call_raw_callback, search_dict


def test_call_callback_none_returns_false() -> None:
    assert call_callback(None, "result", "uuid", "name") is False


def test_call_raw_callback_unknown_type_returns_false() -> None:
    assert call_raw_callback(callback=42) is False


def test_call_raw_callback_with_plain_callable() -> None:
    received: list[object] = []

    def cb(message: object) -> None:
        received.append(message)

    assert call_raw_callback(callback=cb, result="payload") is True
    assert received == ["payload"]


def test_call_callback_swallows_exception(caplog: pytest.LogCaptureFixture) -> None:
    def cb(_message: object) -> None:
        raise RuntimeError("boom")

    with caplog.at_level(logging.ERROR):
        assert call_callback(cb, "x", "uuid", "name") is False
    assert "Exception in name" in caplog.text


def test_call_callback_logs_when_raw_returns_false(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.ERROR):
        assert call_callback(42, "x", "uuid", "named") is False
    assert "named was not called" in caplog.text


@pytest.mark.asyncio
async def test_call_raw_callback_with_future() -> None:
    loop = asyncio.get_running_loop()
    fut: asyncio.Future = loop.create_future()
    assert call_raw_callback(callback=fut, result="value") is True
    assert fut.done()
    assert fut.result() == "value"


@pytest.mark.asyncio
async def test_call_raw_callback_with_already_done_future() -> None:
    """A future that already has a result is left untouched."""
    loop = asyncio.get_running_loop()
    fut: asyncio.Future = loop.create_future()
    fut.set_result("original")
    assert call_raw_callback(callback=fut, result="ignored") is True
    assert fut.result() == "original"


@pytest.mark.asyncio
async def test_call_raw_callback_with_event() -> None:
    event = asyncio.Event()
    assert call_raw_callback(callback=event) is True
    assert event.is_set()


@pytest.mark.asyncio
async def test_call_raw_callback_with_coroutine_function() -> None:
    seen: list[object] = []

    async def coro(message: object) -> None:
        seen.append(message)

    assert call_raw_callback(callback=coro, result="hi") is True
    # Allow scheduled task to run (no eager start on 3.11).
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert seen == ["hi"]


def test_search_dict_finds_match() -> None:
    needles = [
        {"id": 1, "name": "tv"},
        {"id": 2, "name": "stereo"},
        {"id": 3, "name": "lamp"},
    ]
    assert search_dict(match_value=2, key="id", search_list=needles) == {
        "id": 2,
        "name": "stereo",
    }


def test_search_dict_returns_first_match_only() -> None:
    needles = [
        {"id": 1, "tag": "a"},
        {"id": 1, "tag": "b"},
    ]
    result = search_dict(match_value=1, key="id", search_list=needles)
    assert result == {"id": 1, "tag": "a"}


def test_search_dict_returns_none_when_not_found() -> None:
    assert (
        search_dict(match_value="missing", key="id", search_list=[{"id": "other"}])
        is None
    )


def test_search_dict_missing_args_returns_none() -> None:
    assert search_dict() is None
    assert search_dict(match_value=1) is None
    assert search_dict(key="id") is None
    assert search_dict(match_value=1, key="id") is None
    assert search_dict(search_list=[{"id": 1}]) is None


def test_search_dict_raises_on_missing_key() -> None:
    """Documented contract: KeyError surfaces when the key is missing in a row.

    The function uses ``element[key]`` which raises ``KeyError`` when the key
    is absent from a row. This test pins that behavior so callers know to
    only pass uniform dictionaries.
    """
    with pytest.raises(KeyError):
        search_dict(match_value=1, key="id", search_list=[{"other": 1}])
