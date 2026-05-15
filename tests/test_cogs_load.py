"""Offline cog-load + wiring tests.

Asserts every cog loads via ``bot.load_extension`` WITHOUT connecting to
Discord, and that the expected commands, event listeners, and task loops
end up wired to the bot.

Inspection must happen INSIDE the ``async with main.bot:`` block — its
``__aexit__`` calls ``bot.close()``, which clears cog state. A single
module-scoped fixture loads all extensions once and snapshots the bot's
state for every test to assert on.
"""
import asyncio

import pytest


EXPECTED_COGS = {
    'CoreCog', 'ModerationCog', 'ActivityCog', 'PointsCog',
    'SavesCog', 'ServerEventsCog', 'ChallengesCog', 'VerificationCog',
}

EXPECTED_COMMANDS = {
    # CoreCog
    'load_role_relations', 'p', 'force_check_all', 'test', 'force_reactions', 'update',
    # ModerationCog
    'van', 'war', 'pin', 'unpin', 'kick', 'ban', 'mute', 'unmute',
    'warn', 'warns', 'clear_warns', 'lock', 'unlock', 'r',
    # ActivityCog
    'check', 'check_inactive_people', 'unavailable',
    # PointsCog
    'points', 'pts', 'stats',
    # SavesCog
    'save', 'rename', 'disband',
    # ChallengesCog
    'create_challenge',
}

# Events that must have at least one listener after extensions load.
EXPECTED_LISTENERS = {
    # CoreCog
    'on_ready', 'on_command_error',
    # ActivityCog
    'on_voice_state_update',
    'on_raw_reaction_add', 'on_raw_reaction_remove',
    # ServerEventsCog
    'on_member_update', 'on_member_join', 'on_member_remove',
    'on_message',          # also: modules.verification's @bot.listen
    'on_message_edit',     # only: modules.verification's @bot.listen
    'on_socket_raw_receive',
    'on_audit_log_entry_create',
    # VerificationCog
    'on_thread_create',
}


@pytest.fixture(scope='module')
def bot_state():
    """Load every extension once and snapshot the resulting bot state."""
    import main
    from modules import verification

    async def _go():
        async with main.bot:
            for ext in main.EXTENSIONS:
                await main.bot.load_extension(ext)
            return {
                'cogs': set(main.bot.cogs.keys()),
                'commands': set(main.bot.all_commands.keys()),
                'listener_counts': {k: len(v) for k, v in main.bot.extra_events.items()},
                'pings': getattr(main.bot, 'pings', None),
                'polling_loop_exists': hasattr(verification, 'video_polling_loop'),
                'polling_loop_running': verification.video_polling_loop.is_running(),
            }

    return asyncio.run(_go())


def test_all_cogs_load(bot_state):
    assert bot_state['cogs'] == EXPECTED_COGS, (
        f"missing {EXPECTED_COGS - bot_state['cogs']}, "
        f"extra {bot_state['cogs'] - EXPECTED_COGS}"
    )


def test_all_commands_registered(bot_state):
    assert bot_state['commands'] == EXPECTED_COMMANDS, (
        f"missing {EXPECTED_COMMANDS - bot_state['commands']}, "
        f"extra {bot_state['commands'] - EXPECTED_COMMANDS}"
    )


def test_all_expected_listeners_present(bot_state):
    for event in EXPECTED_LISTENERS:
        assert bot_state['listener_counts'].get(event, 0) >= 1, (
            f"no listener registered for {event}"
        )


def test_on_message_has_two_listeners(bot_state):
    # The cog's on_message and modules.verification's @bot.listen('on_message')
    # are both additive and must coexist.
    assert bot_state['listener_counts'].get('on_message', 0) == 2


def test_bot_pings_flag_initialised(bot_state):
    assert bot_state['pings'] is True


def test_video_polling_loop_owned_by_module_and_not_running(bot_state):
    assert bot_state['polling_loop_exists']
    assert bot_state['polling_loop_running'] is False
