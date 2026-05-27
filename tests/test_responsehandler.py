"""Tests for ``aioharmony.responsehandler``.

These tests focus on the pure matching/registration logic and the async
dispatch loop, exercised end-to-end via the queue.
"""

import asyncio
import re
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest_asyncio

from aioharmony.handler import Handler
from aioharmony.responsehandler import ResponseHandler


@pytest_asyncio.fixture
async def rh_pair() -> AsyncIterator[tuple[ResponseHandler, asyncio.Queue]]:
    queue: asyncio.Queue = asyncio.Queue()
    rh = ResponseHandler(message_queue=queue, name="test")
    yield rh, queue
    await rh.close()
    await asyncio.sleep(0)


async def _wait_until(predicate: Callable[[], object], *, timeout: float = 1.0) -> bool:
    """Yield to the event loop until ``predicate()`` returns truthy."""
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            return False
        await asyncio.sleep(0.01)
    return True


def _make_handler(
    callback: Any,
    name: str = "cb",
    resp_json: dict | None = None,
    once: bool = False,
    expiration: timedelta | datetime | None = None,
) -> Handler:
    return Handler(
        handler_obj=callback,
        handler_name=name,
        resp_json=resp_json,
        once=once,
        expiration=expiration,
    )


async def test_register_handler_returns_uuid(
    rh_pair: tuple[ResponseHandler, asyncio.Queue],
) -> None:
    rh, _ = rh_pair
    handler = _make_handler(lambda _msg: None)
    handler_uuid = rh.register_handler(handler=handler)
    assert isinstance(handler_uuid, str)
    assert len(handler_uuid) == 36  # uuid4 string


async def test_unregister_handler_removes_entry(
    rh_pair: tuple[ResponseHandler, asyncio.Queue],
) -> None:
    rh, _ = rh_pair
    handler_uuid = rh.register_handler(handler=_make_handler(lambda _msg: None))
    assert rh.unregister_handler(handler_uuid) is True
    assert rh.unregister_handler(handler_uuid) is False


async def test_unregister_unknown_uuid_returns_false(
    rh_pair: tuple[ResponseHandler, asyncio.Queue],
) -> None:
    rh, _ = rh_pair
    assert rh.unregister_handler("does-not-exist") is False


async def test_register_with_timedelta_expiration_fires_then_removed(
    rh_pair: tuple[ResponseHandler, asyncio.Queue],
) -> None:
    """Handler expiring far in the future fires; one with negative delta does not."""
    rh, queue = rh_pair
    seen: list[dict] = []
    rh.register_handler(
        handler=_make_handler(seen.append, resp_json={"type": "x"}),
        expiration=timedelta(seconds=30),
    )
    await queue.put({"type": "x"})
    await _wait_until(lambda: seen)
    assert seen == [{"type": "x"}]


async def test_register_with_naive_datetime_assumed_utc(
    rh_pair: tuple[ResponseHandler, asyncio.Queue],
) -> None:
    """Naive datetimes in the future allow the callback to fire."""
    rh, queue = rh_pair
    seen: list[dict] = []
    future = (datetime.now(timezone.utc) + timedelta(seconds=60)).replace(tzinfo=None)
    rh.register_handler(
        handler=_make_handler(seen.append, resp_json={"type": "y"}),
        expiration=future,
    )
    await queue.put({"type": "y"})
    await _wait_until(lambda: seen)
    assert seen == [{"type": "y"}]


async def test_handler_expiration_overrides_handler_default(
    rh_pair: tuple[ResponseHandler, asyncio.Queue],
) -> None:
    """When ``register_handler(expiration=...)`` is set, it wins over the Handler's own."""
    rh, queue = rh_pair
    seen: list[dict] = []
    handler = _make_handler(
        seen.append, resp_json={"type": "z"}, expiration=timedelta(seconds=30)
    )
    # Override with an already-expired duration; callback must not fire.
    rh.register_handler(handler=handler, expiration=timedelta(seconds=-1))
    await queue.put({"type": "z"})
    # Give the loop a moment.
    await asyncio.sleep(0.05)
    assert seen == []


async def test_handler_matches_on_resp_json_pattern(
    rh_pair: tuple[ResponseHandler, asyncio.Queue],
) -> None:
    rh, queue = rh_pair
    seen: list[dict] = []
    rh.register_handler(
        handler=_make_handler(
            seen.append, resp_json={"type": re.compile(r"^foo\.bar$")}
        )
    )

    await queue.put({"type": "foo.bar", "data": 1})
    await queue.put({"type": "other"})
    await _wait_until(lambda: seen)
    # Let the loop drain to ensure "other" had a chance.
    await asyncio.sleep(0.02)
    assert seen == [{"type": "foo.bar", "data": 1}]


async def test_handler_msgid_filter(
    rh_pair: tuple[ResponseHandler, asyncio.Queue],
) -> None:
    rh, queue = rh_pair
    seen: list[dict] = []
    rh.register_handler(
        handler=_make_handler(seen.append, name="msgid"),
        msgid="abc-123",
    )

    await queue.put({"id": "abc-123", "payload": True})
    await queue.put({"id": "other", "payload": False})
    await queue.put({"payload": "missing-id"})

    await _wait_until(lambda: seen)
    await asyncio.sleep(0.02)
    assert seen == [{"id": "abc-123", "payload": True}]


async def test_handler_once_removed_after_fire(
    rh_pair: tuple[ResponseHandler, asyncio.Queue],
) -> None:
    rh, queue = rh_pair
    seen: list[dict] = []
    rh.register_handler(
        handler=_make_handler(seen.append, resp_json={"type": "x"}, once=True)
    )
    await queue.put({"type": "x", "n": 1})
    await queue.put({"type": "x", "n": 2})
    await _wait_until(lambda: seen)
    await asyncio.sleep(0.02)
    # The once flag means the second message has no registered handler.
    assert seen == [{"type": "x", "n": 1}]


async def test_handler_persistent_when_not_once(
    rh_pair: tuple[ResponseHandler, asyncio.Queue],
) -> None:
    rh, queue = rh_pair
    seen: list[dict] = []
    rh.register_handler(
        handler=_make_handler(seen.append, resp_json={"type": "x"}, once=False)
    )
    await queue.put({"type": "x", "n": 1})
    await queue.put({"type": "x", "n": 2})
    await _wait_until(lambda: len(seen) == 2)
    assert seen == [{"type": "x", "n": 1}, {"type": "x", "n": 2}]


async def test_handler_match_nested_dict_with_pattern(
    rh_pair: tuple[ResponseHandler, asyncio.Queue],
) -> None:
    rh, queue = rh_pair
    seen: list[dict] = []
    rh.register_handler(
        handler=_make_handler(
            seen.append,
            resp_json={
                "type": re.compile(r"^state$"),
                "data": {"activityStatus": 1},
            },
        )
    )
    await queue.put({"type": "state", "data": {"activityStatus": 1}})
    await queue.put({"type": "state", "data": {"activityStatus": 2}})
    await _wait_until(lambda: seen)
    await asyncio.sleep(0.02)
    assert seen == [{"type": "state", "data": {"activityStatus": 1}}]


async def test_expired_handler_does_not_fire(
    rh_pair: tuple[ResponseHandler, asyncio.Queue],
) -> None:
    rh, queue = rh_pair
    seen: list[dict] = []
    rh.register_handler(
        handler=_make_handler(seen.append, resp_json={"type": "x"}),
        expiration=timedelta(seconds=-1),
    )
    await queue.put({"type": "x"})
    # Drain the loop; ensure nothing fires.
    await asyncio.sleep(0.05)
    assert seen == []


async def test_handler_no_match_when_type_differs(
    rh_pair: tuple[ResponseHandler, asyncio.Queue],
) -> None:
    """value=dict and message=str at the same key should not match."""
    rh, queue = rh_pair
    seen: list[dict] = []
    rh.register_handler(
        handler=_make_handler(seen.append, resp_json={"data": {"key": 1}})
    )
    await queue.put({"data": "not-a-dict"})
    await asyncio.sleep(0.05)
    assert seen == []


async def test_handler_no_match_when_key_missing(
    rh_pair: tuple[ResponseHandler, asyncio.Queue],
) -> None:
    rh, queue = rh_pair
    seen: list[dict] = []
    rh.register_handler(handler=_make_handler(seen.append, resp_json={"data": "x"}))
    await queue.put({"other": "x"})
    await asyncio.sleep(0.05)
    assert seen == []


async def test_callback_exceptions_do_not_break_dispatch(
    rh_pair: tuple[ResponseHandler, asyncio.Queue],
) -> None:
    """A throwing callback for one handler must not prevent others from firing."""
    rh, queue = rh_pair
    seen: list[dict] = []

    class _BadHandler(RuntimeError):
        pass

    def boom(_msg: object) -> None:
        raise _BadHandler

    rh.register_handler(handler=_make_handler(boom, resp_json={"type": "x"}))
    rh.register_handler(handler=_make_handler(seen.append, resp_json={"type": "x"}))

    await queue.put({"type": "x"})
    await _wait_until(lambda: seen)
    assert seen == [{"type": "x"}]


async def test_close_stops_processing_messages(
    rh_pair: tuple[ResponseHandler, asyncio.Queue],
) -> None:
    """After ``close()``, queued messages must not invoke callbacks."""
    rh, queue = rh_pair
    seen: list[dict] = []
    rh.register_handler(
        handler=_make_handler(seen.append, resp_json={"type": "x"}, once=False)
    )
    await rh.close()
    # Let the cancellation take effect.
    await asyncio.sleep(0)
    await queue.put({"type": "x"})
    await asyncio.sleep(0.05)
    assert seen == []
