"""Unit tests for the pure helpers in modules/moderation.py."""
import datetime

import pytest

from modules.moderation import format_timedelta, get_timeout_duration


# ── get_timeout_duration ────────────────────────────────────────────────────


@pytest.mark.parametrize('input_str,expected', [
    ('30s', datetime.timedelta(seconds=30)),
    ('5m', datetime.timedelta(minutes=5)),
    ('2h', datetime.timedelta(hours=2)),
    ('3d', datetime.timedelta(days=3)),
    ('1w', datetime.timedelta(weeks=1)),
    ('4w', datetime.timedelta(weeks=4)),    # exactly 28 days — at the limit
    ('28d', datetime.timedelta(days=28)),   # ditto via day suffix
    ('max', datetime.timedelta(days=28)),
])
def test_get_timeout_duration_valid(input_str, expected):
    assert get_timeout_duration(input_str) == expected


@pytest.mark.parametrize('input_str', [
    '0s', '0m', '0h', '0d', '0w',  # zero-duration -> falsy -> "wrong format"
    'garbage',                      # no recognised suffix
    '5x',                           # unrecognised suffix
    '29d',                          # > 28d
    '5w',                           # 35d > 28d
])
def test_get_timeout_duration_invalid_raises(input_str):
    with pytest.raises(ValueError):
        get_timeout_duration(input_str)


# ── format_timedelta ────────────────────────────────────────────────────────


@pytest.mark.parametrize('td,expected', [
    (datetime.timedelta(0), '0 sec'),
    (datetime.timedelta(seconds=30), '30 sec'),
    (datetime.timedelta(minutes=5), '5 min'),
    (datetime.timedelta(hours=2), '2 hours'),
    (datetime.timedelta(hours=1), '1 hour'),               # singular
    (datetime.timedelta(days=1), '1 day'),                 # singular
    (datetime.timedelta(days=2), '2 days'),                # plural
    (datetime.timedelta(days=1, hours=2, minutes=30, seconds=15),
     '1 day, 2 hours, 30 min, 15 sec'),
])
def test_format_timedelta(td, expected):
    assert format_timedelta(td) == expected
