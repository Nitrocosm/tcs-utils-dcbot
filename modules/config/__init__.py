"""Configuration package.

Re-exports the full public surface so existing ``config.X`` access keeps
working unchanged after the split into settings / ids / messages.

If the environment variable ``STAGING_IDS`` is set (any truthy value), the
IDs are loaded from ``ids_staging.py`` instead of ``ids.py``. Generate that
file once with ``scripts/setup_staging.py <guild_id>``.
"""
import os

from dotenv import dotenv_values

# Check both .env file and shell env. Must read .env directly because nothing
# has called load_dotenv() yet at this point in startup — the bot's first
# `from modules import config` import runs before main.py's logging_config
# (which is where dotenv would normally get loaded).
_env = dotenv_values(".env")
_use_staging = bool(_env.get("STAGING_IDS") or os.getenv("STAGING_IDS"))

if _use_staging:
    from modules.config.ids_staging import (  # type: ignore[import-not-found]
        FORUM_CHANNEL_TAG_IDS,
        INTERESTED_MESSAGE_BASE,
        INTERESTED_MESSAGE_STAR,
        INTERESTED_MESSAGE_ULTIMATE,
        OWNER_ID,
        REACTION_ROLES,
        RELATIONS_CHANNEL_ID,
        VERIFICATION_FORUM_ID,
        WARDROBE_CHANNEL_ID,
        channels,
        emoji,
        roles,
    )
else:
    from modules.config.ids import (
        FORUM_CHANNEL_TAG_IDS,
        INTERESTED_MESSAGE_BASE,
        INTERESTED_MESSAGE_STAR,
        INTERESTED_MESSAGE_ULTIMATE,
        OWNER_ID,
        REACTION_ROLES,
        RELATIONS_CHANNEL_ID,
        VERIFICATION_FORUM_ID,
        WARDROBE_CHANNEL_ID,
        channels,
        emoji,
        roles,
    )
from modules.config.messages import message, verification_messages
from modules.config.settings import TARGET_GUILD, TOKEN, check_guild

__all__ = [
    'TARGET_GUILD',
    'TOKEN',
    'check_guild',
    'roles',
    'channels',
    'emoji',
    'message',
    'verification_messages',
    'OWNER_ID',
    'REACTION_ROLES',
    'FORUM_CHANNEL_TAG_IDS',
    'VERIFICATION_FORUM_ID',
    'RELATIONS_CHANNEL_ID',
    'WARDROBE_CHANNEL_ID',
    'INTERESTED_MESSAGE_BASE',
    'INTERESTED_MESSAGE_STAR',
    'INTERESTED_MESSAGE_ULTIMATE',
]
