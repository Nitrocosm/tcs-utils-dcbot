"""Unit tests for the modules/config package."""
from modules import config
from modules.config import TARGET_GUILD, check_guild


def test_check_guild_target_returns_true():
    assert check_guild(TARGET_GUILD) is True


def test_check_guild_other_returns_false():
    assert check_guild(0) is False
    assert check_guild(99999) is False
    assert check_guild(TARGET_GUILD + 1) is False


def test_public_surface_complete():
    """The package's __init__ re-exports everything the rest of the codebase needs."""
    for name in (
        'TARGET_GUILD', 'TOKEN', 'check_guild',
        'roles', 'channels', 'emoji',
        'message', 'verification_messages',
        'OWNER_ID', 'REACTION_ROLES', 'FORUM_CHANNEL_TAG_IDS',
    ):
        assert hasattr(config, name), f'config.{name} missing'


def test_no_duplicate_role_values_with_distinct_keys():
    # The Phase 1.3 cleanup removed completion_server_star_star /
    # completion_server_base_star which were duplicate values under different
    # keys. Lock that in so they don't sneak back.
    assert 'completion_server_star_star' not in config.roles
    assert 'completion_server_base_star' not in config.roles


def test_message_returns_string_and_formats_kwargs():
    out = config.message('promotion', mention='@x')
    assert isinstance(out, str)
    assert '@x' in out
