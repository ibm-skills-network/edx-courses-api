"""
Tests for request parameter parsing in ``edx_courses_api.params``.
"""
import pytest

from edx_courses_api.params import first_present, parse_bool


@pytest.mark.parametrize("value, expected", [
    (True, True),
    (False, False),
    ("true", True),
    ("True", True),
    (" false ", False),
    ("1", True),
    ("0", False),
])
def test_parse_bool_accepts_booleans_and_strings(value, expected):
    assert parse_bool(value) is expected


# 1 and 0 are here because the strings "1" and "0" pass. The ints must not.
@pytest.mark.parametrize("value", [None, "", "maybe", 1, 0, [], {}])
def test_parse_bool_rejects_other_values(value):
    assert parse_bool(value) is None


def test_first_present_takes_the_first_key_found():
    assert first_present({"certificate": False, "enabled": True}, ("enabled", "certificate")) is True


# A present False must be returned as False, not skipped as if missing.
def test_first_present_keeps_a_false_value():
    assert first_present({"certificate": False}, ("enabled", "certificate")) is False


def test_first_present_returns_none_when_no_key_matches():
    assert first_present({"name": "x"}, ("enabled", "certificate")) is None


# "enabled" is a substring of the body string, and 5 cannot be searched with `in` at all.
# Both must come back as None, not a crash.
@pytest.mark.parametrize("data", ["enabled", 5, ["enabled"]])
def test_first_present_returns_none_for_a_body_that_is_not_an_object(data):
    assert first_present(data, ("enabled",)) is None
