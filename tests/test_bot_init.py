"""Phase 6.1 — pin the intent shape.

The bot only needs the intents whose events it actually subscribes to.
`presences` was previously enabled but unread; dropping it reduces the
gateway traffic Discord sends us and the bot's privileged-intent surface.
"""
from modules.bot_init import bot


def test_presences_intent_disabled():
    assert bot.intents.presences is False, (
        "presences intent must stay off — nothing reads member presence/activity"
    )


def test_required_intents_enabled():
    # These are the intents whose events the bot actually listens for.
    assert bot.intents.members is True
    assert bot.intents.message_content is True
    assert bot.intents.reactions is True
    assert bot.intents.guilds is True
