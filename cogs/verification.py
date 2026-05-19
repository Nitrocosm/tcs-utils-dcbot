"""VerificationCog — thin wiring cog for the verification feature.

Owns only the ``on_thread_create`` listener: it dispatches new threads in
the verification forum to ``modules.verification.start_verification_flow``
and auto-applies tags to threads in other configured forums.

``modules/verification.py`` keeps all the heavy logic (state machine,
Views, ``video_polling_loop``) and continues to self-register its own
``@bot.listen('on_message')`` / ``@bot.listen('on_message_edit')`` /
``@tasks.loop`` decorators when ``main.py`` imports it. A follow-up
"Phase 2.5" — after Phase 5 lands a pure-logic test suite — will move
that wiring into this cog so verification looks like every other cog.
"""
import asyncio
import logging

import discord
from discord.ext import commands

from modules import config, verification

log = logging.getLogger(__name__)


class VerificationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        await asyncio.sleep(1)
        if not isinstance(thread.parent, discord.ForumChannel):
            return
        if thread.parent_id == verification.VERIFICATION_FORUM_ID:
            await verification.start_verification_flow(thread)
            return
        if thread.parent_id not in config.FORUM_CHANNEL_TAG_IDS:
            return

        tag = thread.parent.get_tag(config.FORUM_CHANNEL_TAG_IDS[thread.parent_id])
        if tag:
            current_tags = thread.applied_tags
            if tag not in current_tags:
                current_tags.append(tag)
                await thread.edit(applied_tags=current_tags)

        await thread.send(f"<@&{config.roles['verifier']}> new challenge to verify")


async def setup(bot: commands.Bot):
    await bot.add_cog(VerificationCog(bot))
