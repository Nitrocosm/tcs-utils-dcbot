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
    'cogs.verification',
]








async def main():
    async with bot:
        for ext in EXTENSIONS:
            await bot.load_extension(ext)
        await bot.start(config.TOKEN)


if __name__ == '__main__':
    asyncio.run(main())