"""Configuration package.

Re-exports the full public surface so existing ``config.X`` access keeps
working unchanged after the split into settings / ids / messages.
"""
from modules.config.ids import (
    FORUM_CHANNEL_TAG_IDS,
    OWNER_ID,
    REACTION_ROLES,
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
]
