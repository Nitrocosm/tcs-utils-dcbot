"""Entry point for tcs-utils-dcbot.

Sets up logging, loads cog extensions, and starts the bot. All commands and
event handlers live in the ``cogs/`` package; ``modules/`` holds the business
logic.

``modules.verification`` is imported for its side-effect of self-registering
its own ``@bot.listen`` / ``@tasks.loop`` hooks at import time. That wiring
has not yet moved into a cog — see "Phase 2.5" in the refactor plan, which
will migrate it once Phase 5 lands the pure-logic test suite.
"""
import asyncio

import modules.verification  # noqa: F401 -- side-effect: registers @bot.listen / @tasks.loop
from modules import config, logging_config
from modules.bot_init import bot

logging_config.setup()
bot.pings = True

EXTENSIONS: list[str] = [
    'cogs.core',
    'cogs.moderation',
    'cogs.activity',
    'cogs.points',
    'cogs.saves',
    'cogs.server_events',
    'cogs.challenges',
    'cogs.verification',
]


async def main():
    async with bot:
        for ext in EXTENSIONS:
            await bot.load_extension(ext)
        await bot.start(config.TOKEN)


if __name__ == '__main__':
    asyncio.run(main())
