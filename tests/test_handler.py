"""Tests for the Handler module."""

import copy
import re
from datetime import timedelta

import pytest

from aioharmony import handler as handler_module
from aioharmony.handler import (
    DEFAULT_TIMEOUT,
    HANDLER_HELPDISCRETES,
    HANDLER_NOTIFY,
    HANDLER_RUN_ACTIVITY,
    HANDLER_START_ACTIVITY_COMPLETE,
    HANDLER_START_ACTIVITY_FINISHED,
    HANDLER_START_ACTIVITY_IN_PROGRESS,
    HANDLER_START_ACTIVITY_NOTIFY_INPROGRESS,
    HANDLER_START_ACTIVITY_NOTIFY_STARTED,
    HANDLER_STOP_ACTIVITY_NOTIFY_STARTED,
    Handler,
    dummy_callback,
)


def _noop(message):
    return message


def test_init_defaults():
    h = Handler(handler_obj=_noop)
    assert h.handler_obj is _noop
    assert h.handler_name is None
    assert h.resp_json is None
    assert h.once is True
    assert h.expiration is None


def test_init_all_fields():
    expiration = timedelta(seconds=30)
    h = Handler(
        handler_obj=_noop,
        handler_name="name",
        resp_json={"k": "v"},
        once=False,
        expiration=expiration,
    )
    assert h.handler_name == "name"
    assert h.resp_json == {"k": "v"}
    assert h.once is False
    assert h.expiration is expiration


def test_setters_roundtrip():
    h = Handler(handler_obj=_noop)
    h.handler_obj = dummy_callback
    h.handler_name = "renamed"
    h.resp_json = {"a": 1}
    h.once = False
    h.expiration = timedelta(seconds=5)

    assert h.handler_obj is dummy_callback
    assert h.handler_name == "renamed"
    assert h.resp_json == {"a": 1}
    assert h.once is False
    assert h.expiration == timedelta(seconds=5)


def test_copy_clones_resp_json_dict():
    original = Handler(handler_obj=_noop, resp_json={"k": "v"})
    dup = copy.copy(original)

    assert dup is not original
    assert dup.resp_json == {"k": "v"}
    assert dup.resp_json is not original.resp_json

    dup.resp_json["k"] = "changed"
    assert original.resp_json == {"k": "v"}


def test_copy_preserves_all_fields():
    expiration = timedelta(seconds=12)
    original = Handler(
        handler_obj=_noop,
        handler_name="orig",
        resp_json={"x": 1},
        once=False,
        expiration=expiration,
    )
    dup = copy.copy(original)

    assert dup.handler_obj is _noop
    assert dup.handler_name == "orig"
    assert dup.once is False
    assert dup.expiration is expiration


def test_copy_handles_none_resp_json():
    original = Handler(handler_obj=_noop)
    assert original.resp_json is None

    dup = copy.copy(original)
    assert dup is not original
    assert dup.resp_json is None


def test_dummy_callback_returns_input():
    payload = {"hello": "world"}
    assert dummy_callback(payload) is payload


def test_default_timeout_constant():
    assert DEFAULT_TIMEOUT == 60


@pytest.mark.parametrize(
    ("constant", "expected_name"),
    [
        (HANDLER_NOTIFY, "Notification_Received"),
        (HANDLER_START_ACTIVITY_NOTIFY_STARTED, "Activity_Starting"),
        (HANDLER_STOP_ACTIVITY_NOTIFY_STARTED, "Activity_Stopping"),
        (HANDLER_START_ACTIVITY_NOTIFY_INPROGRESS, "Activity_Starting_Inprogress"),
        (HANDLER_START_ACTIVITY_FINISHED, "Activity_Changed"),
        (HANDLER_RUN_ACTIVITY, "runactivity"),
        (HANDLER_START_ACTIVITY_IN_PROGRESS, "progress_startactivity"),
        (HANDLER_HELPDISCRETES, "progress_discrete"),
        (HANDLER_START_ACTIVITY_COMPLETE, "startactivity_or_discrete"),
    ],
)
def test_module_handler_constants(constant, expected_name):
    assert isinstance(constant, Handler)
    assert constant.handler_name == expected_name
    assert constant.once is False
    assert isinstance(constant.resp_json, dict)


@pytest.mark.parametrize(
    ("constant", "sample_payload"),
    [
        (HANDLER_NOTIFY, {"type": "connect.stateDigest?notify"}),
        (
            HANDLER_START_ACTIVITY_NOTIFY_STARTED,
            {"type": "connect.stateDigest?notify"},
        ),
        (
            HANDLER_START_ACTIVITY_FINISHED,
            {"type": "harmony.engine?startActivityFinished"},
        ),
    ],
)
def test_handler_resp_json_patterns_match_expected(constant, sample_payload):
    pattern = constant.resp_json["type"]
    assert isinstance(pattern, re.Pattern)
    assert pattern.match(sample_payload["type"])


def test_long_lived_handlers_have_expiration():
    long_lived = (
        HANDLER_RUN_ACTIVITY,
        HANDLER_START_ACTIVITY_IN_PROGRESS,
        HANDLER_HELPDISCRETES,
        HANDLER_START_ACTIVITY_COMPLETE,
    )
    for h in long_lived:
        assert h.expiration == timedelta(seconds=DEFAULT_TIMEOUT * 5)


def test_notify_handlers_have_no_expiration():
    no_expiry = (
        HANDLER_NOTIFY,
        HANDLER_START_ACTIVITY_NOTIFY_STARTED,
        HANDLER_STOP_ACTIVITY_NOTIFY_STARTED,
        HANDLER_START_ACTIVITY_NOTIFY_INPROGRESS,
        HANDLER_START_ACTIVITY_FINISHED,
    )
    for h in no_expiry:
        assert h.expiration is None


def test_no_duplicate_handler_names_in_module():
    """Each module-level HANDLER_* constant should be uniquely named."""
    handler_attrs = {
        name: getattr(handler_module, name)
        for name in dir(handler_module)
        if name.startswith("HANDLER_")
    }
    assert len(handler_attrs) == 9
    handler_ids = {id(h) for h in handler_attrs.values()}
    assert len(handler_ids) == len(handler_attrs)


def test_activity_status_codes_distinct():
    started = HANDLER_START_ACTIVITY_NOTIFY_STARTED.resp_json["data"]["activityStatus"]
    stopped = HANDLER_STOP_ACTIVITY_NOTIFY_STARTED.resp_json["data"]["activityStatus"]
    inprogress = HANDLER_START_ACTIVITY_NOTIFY_INPROGRESS.resp_json["data"][
        "activityStatus"
    ]
    assert {started, stopped, inprogress} == {0, 1, 2}
