"""Unit tests for the pure helpers in modules/points.py."""
from unittest.mock import MagicMock

import pytest

from modules.points import (
    calculate_points,
    get_leaderboard,
    get_member_rank,
    get_ranked_leaderboard,
    has_all_challenges,
    parse_challenge_role,
)


# ── helpers ────────────────────────────────────────────────────────────────


def make_role(name: str, role_id: int = 1) -> MagicMock:
    r = MagicMock()
    r.name = name
    r.id = role_id
    return r


def make_member(name: str, member_id: int, roles: list, is_bot: bool = False) -> MagicMock:
    m = MagicMock()
    m.display_name = name
    m.id = member_id
    m.roles = roles
    m.bot = is_bot
    m.mention = f'<@{member_id}>'
    return m


# ── parse_challenge_role ───────────────────────────────────────────────────


@pytest.mark.parametrize('name,expected', [
    # official base / star / ultimate
    ('🏆🟢 Door of Hope /+5/', {'tier_emoji': '🟢', 'name': 'Door of Hope', 'points': 5}),
    ('🏆⭐ Hard Mode /+15/',   {'tier_emoji': '⭐', 'name': 'Hard Mode', 'points': 15}),
    ('🏆☄ The Hardest /+25/', {'tier_emoji': '☄', 'name': 'The Hardest', 'points': 25}),
    # custom (diamond prefix)
    ('💠🟢 Custom Run /+3/',  {'tier_emoji': '🟢', 'name': 'Custom Run', 'points': 3}),
    ('💠⭐ Custom Star /+10/', {'tier_emoji': '⭐', 'name': 'Custom Star', 'points': 10}),
])
def test_parse_challenge_role_valid(name, expected):
    r = make_role(name, role_id=42)
    info = parse_challenge_role(r)
    assert info is not None
    assert info['tier_emoji'] == expected['tier_emoji']
    assert info['name'] == expected['name']
    assert info['points'] == expected['points']
    assert info['role'] == 42


@pytest.mark.parametrize('name', [
    'Some Random Role',           # no tier prefix at all
    '🏆 Missing Tier Emoji /+5/', # missing the tier emoji after 🏆
    '🏆🟢 No Points',             # missing /+N/ block
    '🏆🟢 Bad Format +5',         # malformed points
    '⭐ Wrong Prefix /+5/',        # tier emoji at column 0
    '',
])
def test_parse_challenge_role_invalid(name):
    assert parse_challenge_role(make_role(name)) is None


# ── calculate_points ───────────────────────────────────────────────────────


def test_calculate_points_no_challenge_roles():
    m = make_member('alice', 1, roles=[make_role('Just a normal role')])
    assert calculate_points(m) == (0, [])


def test_calculate_points_sums_and_sorts_descending():
    m = make_member('alice', 1, roles=[
        make_role('🏆🟢 Easy /+2/', role_id=11),
        make_role('🏆⭐ Hard /+10/', role_id=22),
        make_role('🏆🟢 Mid /+5/', role_id=33),
        make_role('not a challenge', role_id=99),
    ])
    total, role_ids = calculate_points(m)
    assert total == 17                  # 2 + 10 + 5
    assert role_ids == [22, 33, 11]     # 10 > 5 > 2


# ── get_leaderboard / get_ranked_leaderboard ───────────────────────────────


def _build_guild(*members):
    g = MagicMock()
    g.members = list(members)
    return g


def test_get_leaderboard_excludes_bots_and_zero_score():
    alice = make_member('alice', 1, [make_role('🏆🟢 X /+10/', 100)])
    zero = make_member('zero', 2, [make_role('not a challenge', 200)])  # 0 pts
    bot = make_member('bot', 3, [make_role('🏆🟢 Y /+99/', 300)], is_bot=True)

    lb = get_leaderboard(_build_guild(alice, zero, bot))
    # zero-point members + bots both excluded
    assert lb == [(alice, 10)]


def test_get_ranked_leaderboard_ties():
    alice = make_member('alice', 1, [make_role('🏆🟢 X /+10/', 100)])
    bob   = make_member('bob',   2, [make_role('🏆🟢 Y /+5/',  101)])
    carol = make_member('carol', 3, [make_role('🏆🟢 Z /+5/',  102)])

    ranked = get_ranked_leaderboard(_build_guild(alice, bob, carol))
    # Expected:
    #   rank 1: 10 pts -> [alice]
    #   rank 2: 5 pts  -> [bob, carol]  (tied)
    assert len(ranked) == 2
    assert ranked[0] == (1, 10, [alice])
    assert ranked[1][0] == 2
    assert ranked[1][1] == 5
    assert set(ranked[1][2]) == {bob, carol}


def test_get_member_rank_returns_position():
    alice = make_member('alice', 1, [make_role('🏆🟢 X /+10/', 100)])
    bob   = make_member('bob',   2, [make_role('🏆🟢 Y /+5/',  101)])
    g = _build_guild(alice, bob)

    assert get_member_rank(g, alice) == 1
    assert get_member_rank(g, bob) == 2


def test_get_member_rank_unranked_returns_none():
    alice = make_member('alice', 1, [make_role('🏆🟢 X /+10/', 100)])
    nobody = make_member('nobody', 99, [make_role('not a challenge', 999)])
    g = _build_guild(alice, nobody)
    assert get_member_rank(g, nobody) is None


# ── has_all_challenges ─────────────────────────────────────────────────────


def test_has_all_challenges_returns_false_when_no_required_exist():
    m = make_member('alice', 1, roles=[])
    m.guild = MagicMock(); m.guild.roles = []  # no base challenges in guild
    assert has_all_challenges(m, {'🟢'}) is False


def test_has_all_challenges_all_owned_returns_true():
    challenges = [
        make_role('🏆🟢 A /+5/', 1),
        make_role('🏆🟢 B /+5/', 2),
        make_role('🏆🟢 C /+5/', 3),
    ]
    m = make_member('alice', 1, roles=challenges)
    m.guild = MagicMock(); m.guild.roles = challenges
    assert has_all_challenges(m, {'🟢'}) is True


def test_has_all_challenges_missing_one_returns_false():
    challenges = [
        make_role('🏆🟢 A /+5/', 1),
        make_role('🏆🟢 B /+5/', 2),
        make_role('🏆🟢 C /+5/', 3),
    ]
    m = make_member('alice', 1, roles=challenges[:2])  # missing C
    m.guild = MagicMock(); m.guild.roles = challenges
    assert has_all_challenges(m, {'🟢'}) is False


def test_has_all_challenges_custom_diamond_excluded():
    # 💠-prefixed challenges (custom runs) don't count toward "beat all".
    custom = [make_role('💠🟢 Custom /+5/', 1)]
    m = make_member('alice', 1, roles=[])
    m.guild = MagicMock(); m.guild.roles = custom
    # zero required (because the only role is 💠) -> returns False
    assert has_all_challenges(m, {'🟢'}) is False
