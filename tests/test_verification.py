"""Unit tests for the pure helpers in modules/verification.py.

Covers the YouTube URL parsers, the tiny lookup helpers
(_verifiers_for_points, _verifier_tag, _next_5min_interval), and the
state-machine renderer _build_challenge_message — the function that turns
every verification state into the message the runner sees in the thread.
"""
from unittest.mock import MagicMock, patch

import pytest

from modules import config
from modules.verification import (
    TAG_1_NEEDED,
    TAG_2_NEEDED,
    TAG_3_NEEDED,
    _build_challenge_message,
    _get_youtube_url,
    _get_youtube_video_id,
    _next_5min_interval,
    _verifier_tag,
    _verifiers_for_points,
)

VM = config.verification_messages


# ── YouTube URL parsers ─────────────────────────────────────────────────────


@pytest.mark.parametrize('url,expected_id', [
    ('https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'dQw4w9WgXcQ'),
    ('https://youtube.com/watch?v=ABCdef12345', 'ABCdef12345'),
    ('https://m.youtube.com/watch?v=xxxxxxxxxxx', 'xxxxxxxxxxx'),
    ('https://youtu.be/yyyyyyyyyyy', 'yyyyyyyyyyy'),
    ('https://www.youtube.com/shorts/zzzzzzzzzzz', 'zzzzzzzzzzz'),
    # extra query params don't break extraction
    ('https://youtube.com/watch?v=dQw4w9WgXcQ&t=42s', 'dQw4w9WgXcQ'),
    # http (no s) form
    ('http://youtu.be/yyyyyyyyyyy', 'yyyyyyyyyyy'),
    # bare without scheme
    ('youtu.be/yyyyyyyyyyy', 'yyyyyyyyyyy'),
])
def test_get_youtube_video_id_valid(url, expected_id):
    assert _get_youtube_video_id(url) == expected_id


@pytest.mark.parametrize('text', [
    '',
    'no link here',
    'https://twitch.tv/somestream',
    'https://www.youtube.com/channel/UCabc',         # channel, not video
    'https://youtu.be/short',                         # id < 11 chars
])
def test_get_youtube_video_id_invalid_returns_none(text):
    assert _get_youtube_video_id(text) is None


def test_get_youtube_url_extracts_from_surrounding_text():
    text = 'hey check this out https://www.youtube.com/watch?v=dQw4w9WgXcQ amazing'
    url = _get_youtube_url(text)
    assert url == 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'


def test_get_youtube_url_none_when_no_match():
    assert _get_youtube_url('just text without a link') is None


# ── tiny lookup helpers ─────────────────────────────────────────────────────


@pytest.mark.parametrize('points,expected', [
    (0, 2), (1, 2), (5, 2), (10, 2), (13, 2),  # under-14 -> 2 verifiers
    (14, 3), (17, 3), (24, 3), (100, 3),        # 14+ -> 3 verifiers
])
def test_verifiers_for_points(points, expected):
    assert _verifiers_for_points(points) == expected


@pytest.mark.parametrize('count,expected_tag', [
    (3, TAG_3_NEEDED),
    (2, TAG_2_NEEDED),
    (1, TAG_1_NEEDED),
    (0, TAG_3_NEEDED),   # unknown counts fall back to "3 needed"
    (99, TAG_3_NEEDED),
])
def test_verifier_tag(count, expected_tag):
    assert _verifier_tag(count) == expected_tag


def test_next_5min_interval_is_strictly_in_the_future():
    with patch('modules.verification.time.time', return_value=1000):
        # 1000 // 300 = 3, +1 = 4, *300 = 1200
        assert _next_5min_interval() == 1200


def test_next_5min_interval_strict_future_at_boundary():
    # At an exact 5-min boundary, the next interval is the FOLLOWING one
    with patch('modules.verification.time.time', return_value=1500):
        # 1500 is a multiple of 300; "next" should be 1800, not 1500
        assert _next_5min_interval() == 1800


# ── _build_challenge_message: state-machine renderer ───────────────────────


def _base_state(**overrides):
    """A state dict with sane defaults; override individual keys per test."""
    state = {
        'selected_role_id': None,
        'op_id': 12345,
        'state': '',
        'video_url': None,
        'video_ready': False,
        'verifiers_needed': 0,
        'verifiers_done': 0,
        'last_verifier': None,
        'next_check_at': None,
        'no_footage': False,
    }
    state.update(overrides)
    return state


def _fake_guild_no_role():
    g = MagicMock()
    g.get_role.return_value = None  # forces the renderer's '???' fallback
    return g


def test_build_message_always_includes_header():
    out = _build_challenge_message(_base_state(), _fake_guild_no_role())
    # The "???" fallback fires for both role_mention and name
    assert '???' in out
    assert '<@12345>' in out  # op_mention


def test_build_message_rejected_state():
    out = _build_challenge_message(_base_state(state='rejected'), _fake_guild_no_role())
    assert VM['msg_body_rejected'] in out


def test_build_message_reported_state():
    out = _build_challenge_message(_base_state(state='reported'), _fake_guild_no_role())
    assert VM['msg_body_reported'] in out


def test_build_message_manual_state():
    out = _build_challenge_message(_base_state(state='manual'), _fake_guild_no_role())
    assert VM['msg_body_manual'] in out


def test_build_message_video_ready_includes_progress():
    out = _build_challenge_message(
        _base_state(
            video_url='https://youtu.be/abcdefghijk',
            video_ready=True,
            verifiers_needed=3,
            verifiers_done=1,
        ),
        _fake_guild_no_role(),
    )
    # ready body interpolates done/needed - both must appear
    expected = VM['msg_body_ready'].format(done=1, needed=3)
    assert expected in out
    # URL line is appended whenever a video_url is set
    assert VM['msg_url_line'].format(url='https://youtu.be/abcdefghijk') in out


def test_build_message_video_ready_with_last_verifier():
    out = _build_challenge_message(
        _base_state(
            video_url='https://youtu.be/abcdefghijk',
            video_ready=True,
            verifiers_needed=2,
            verifiers_done=1,
            last_verifier='@somebody',
        ),
        _fake_guild_no_role(),
    )
    assert VM['msg_body_ready_last'].format(last='@somebody') in out


def test_build_message_video_uploading_includes_next_check():
    out = _build_challenge_message(
        _base_state(
            video_url='https://youtu.be/abcdefghijk',
            video_ready=False,
            next_check_at=1700000000,
        ),
        _fake_guild_no_role(),
    )
    assert VM['msg_body_uploading'] in out
    assert VM['msg_body_uploading_check'].format(ts=1700000000) in out


def test_build_message_no_footage_branch():
    out = _build_challenge_message(_base_state(no_footage=True), _fake_guild_no_role())
    assert VM['msg_body_no_footage'] in out


def test_build_message_no_video_default_branch():
    out = _build_challenge_message(_base_state(), _fake_guild_no_role())
    assert VM['msg_body_no_video'] in out


def test_build_message_no_video_with_hint_in_awaiting_video_state():
    out = _build_challenge_message(_base_state(state='awaiting_video'), _fake_guild_no_role())
    assert VM['msg_body_no_video'] in out
    assert VM['msg_body_no_video_hint'] in out


def test_build_message_url_line_only_when_video_url_set():
    # default state has no video_url - url line must NOT appear
    out_no_url = _build_challenge_message(_base_state(), _fake_guild_no_role())
    assert 'msg_url_line' not in out_no_url
    # add a url - it appears
    out_with_url = _build_challenge_message(
        _base_state(video_url='https://youtu.be/xxxxxxxxxxx'),
        _fake_guild_no_role(),
    )
    assert 'https://youtu.be/xxxxxxxxxxx' in out_with_url


def test_build_message_uses_role_name_when_role_resolves():
    """When the guild's get_role returns a parseable challenge role, the
    challenge name appears in the rendered message instead of "???"."""
    fake_role = MagicMock()
    fake_role.name = '🏆🟢 Door of Hope /+5/'
    fake_role.id = 999
    guild = MagicMock()
    guild.get_role.return_value = fake_role

    out = _build_challenge_message(_base_state(selected_role_id=999), guild)
    assert 'Door of Hope' in out
    assert '<@&999>' in out
