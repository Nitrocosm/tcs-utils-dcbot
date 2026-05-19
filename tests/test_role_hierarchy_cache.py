"""Phase 6.3 — role-hierarchy cache.

`_get_role_hierarchy` is called from `_fix_categories` which runs on
every `RoleSession.commit()`. Caching the topology dict avoids
re-sorting and re-iterating `guild.roles` on every commit.
"""
from types import SimpleNamespace
from unittest.mock import patch

from modules import role_management


class _FakeRole:
    """Minimal stand-in for discord.Role — must be hashable (used as dict key)."""
    def __init__(self, name: str, position: int, default: bool = False):
        self.name = name
        self.position = position
        self._default = default

    def is_default(self) -> bool:
        return self._default

    def __repr__(self) -> str:
        return f"<FakeRole {self.name!r}>"


def _make_role(name: str, position: int, default: bool = False) -> _FakeRole:
    return _FakeRole(name, position, default)


def _make_guild(gid: int, roles: list):
    return SimpleNamespace(id=gid, roles=roles)


def setup_function(_):
    role_management.clear_hierarchy_cache()


def test_cache_returns_same_dict_within_ttl():
    guild = _make_guild(
        1,
        [
            _make_role("@everyone", 0, default=True),
            _make_role("Alpha", 9),
            _make_role("──╱ category ─", 10),
        ],
    )
    first = role_management._get_role_hierarchy(guild)
    second = role_management._get_role_hierarchy(guild)
    assert first is second, "subsequent call within TTL must return the cached dict"


def test_clear_one_guild_invalidates_only_that_guild():
    g1 = _make_guild(
        1,
        [
            _make_role("@everyone", 0, default=True),
            _make_role("Alpha", 9),
            _make_role("──╱ a ─", 10),
        ],
    )
    g2 = _make_guild(
        2,
        [
            _make_role("@everyone", 0, default=True),
            _make_role("Beta", 9),
            _make_role("──╱ b ─", 10),
        ],
    )

    cached_g1 = role_management._get_role_hierarchy(g1)
    cached_g2 = role_management._get_role_hierarchy(g2)

    role_management.clear_hierarchy_cache(g1.id)

    assert role_management._get_role_hierarchy(g1) is not cached_g1
    assert role_management._get_role_hierarchy(g2) is cached_g2


def test_clear_all_invalidates_every_guild():
    g1 = _make_guild(1, [_make_role("@everyone", 0, default=True), _make_role("──╱ a ─", 1)])
    g2 = _make_guild(2, [_make_role("@everyone", 0, default=True), _make_role("──╱ b ─", 1)])
    first_g1 = role_management._get_role_hierarchy(g1)
    first_g2 = role_management._get_role_hierarchy(g2)

    role_management.clear_hierarchy_cache()

    assert role_management._get_role_hierarchy(g1) is not first_g1
    assert role_management._get_role_hierarchy(g2) is not first_g2


def test_different_guilds_get_separate_cache_entries():
    g1 = _make_guild(1, [_make_role("@everyone", 0, default=True), _make_role("──╱ a ─", 1)])
    g2 = _make_guild(2, [_make_role("@everyone", 0, default=True), _make_role("──╱ b ─", 1)])
    r1 = role_management._get_role_hierarchy(g1)
    r2 = role_management._get_role_hierarchy(g2)
    assert r1 is not r2
    assert {c.name for c in r1} != {c.name for c in r2}


def test_ttl_expiry_triggers_recompute():
    guild = _make_guild(
        1,
        [_make_role("@everyone", 0, default=True), _make_role("──╱ category ─", 10)],
    )
    with patch.object(role_management.time, "monotonic", return_value=1000.0):
        first = role_management._get_role_hierarchy(guild)
    with patch.object(
        role_management.time,
        "monotonic",
        return_value=1000.0 + role_management._HIERARCHY_TTL_SECONDS + 1,
    ):
        second = role_management._get_role_hierarchy(guild)
    assert first is not second


def test_cached_result_is_byte_for_byte_correct():
    """Cache must not change the shape of the returned dict."""
    cat = _make_role("──╱ category ─", 10)
    alpha = _make_role("Alpha", 9)
    none_role = _make_role("🚫 none", 8)
    everyone = _make_role("@everyone", 0, default=True)
    guild = _make_guild(99, [everyone, none_role, alpha, cat])

    result = role_management._get_role_hierarchy(guild)
    assert cat in result
    assert result[cat]["roles"] == [alpha]
    assert result[cat]["none_role"] is none_role


def test_hierarchy_stops_at_everyone():
    """Roles below @everyone shouldn't get associated with a category."""
    cat = _make_role("──╱ category ─", 10)
    above = _make_role("Above", 9)
    everyone = _make_role("@everyone", 5, default=True)
    below = _make_role("Below", 1)  # below @everyone — should NOT be in any category
    guild = _make_guild(7, [below, everyone, above, cat])

    result = role_management._get_role_hierarchy(guild)
    assert above in result[cat]["roles"]
    assert below not in result[cat]["roles"]


def test_blank_named_roles_are_skipped():
    cat = _make_role("──╱ category ─", 10)
    blank = _make_role("   ", 9)
    alpha = _make_role("Alpha", 8)
    everyone = _make_role("@everyone", 0, default=True)
    guild = _make_guild(8, [everyone, alpha, blank, cat])

    result = role_management._get_role_hierarchy(guild)
    assert blank not in result[cat]["roles"]
    assert alpha in result[cat]["roles"]
