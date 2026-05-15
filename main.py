import asyncio

import discord
from discord import VoiceChannel
from discord.ext import commands
from modules import config, activity, moderation, general, badges, verification, logging_config
from modules.config import TARGET_GUILD
from modules.general import timed_delete_msg, send_timed_delete_msg
from modules.role_management import RoleSession
from modules.saves import create_save, disband_save, rename_save
from modules.points import calculate_points, get_ranked_leaderboard, update_leaderboard_message, parse_challenge_role, get_member_rank, has_all_challenges, LB_EMOJI
from modules.bot_init import bot

logging_config.setup()
bot.pings = True

# Cogs are loaded in main() below. Each commit in Phase 2 appends to this list
# as commands/events migrate out of main.py and into cogs/.
EXTENSIONS: list[str] = [
    'cogs.core',
    'cogs.moderation',
    'cogs.activity',
    'cogs.points',
    'cogs.saves',
    'cogs.server_events',
    'cogs.challenges',
]




# Forum auto-tag mapping is configured in modules/config/ids.py
FORUM_CHANNEL_TAG_IDS = config.FORUM_CHANNEL_TAG_IDS

@bot.event
async def on_thread_create(thread: discord.Thread):
    await asyncio.sleep(1)
    if not isinstance(thread.parent, discord.ForumChannel):
        return
    if thread.parent_id == verification.VERIFICATION_FORUM_ID:
        await verification.start_verification_flow(thread)
        return
    if thread.parent_id not in FORUM_CHANNEL_TAG_IDS:
        return

    tag = thread.parent.get_tag(FORUM_CHANNEL_TAG_IDS[thread.parent_id])
    if tag:
        current_tags = thread.applied_tags
        if tag not in current_tags:
            current_tags.append(tag)
            await thread.edit(applied_tags=current_tags)

    await thread.send(f"<@&{config.roles['verifier']}> new challenge to verify")
    #------------------------------------










async def main():
    async with bot:
        for ext in EXTENSIONS:
            await bot.load_extension(ext)
        await bot.start(config.TOKEN)


if __name__ == '__main__':
    asyncio.run(main())