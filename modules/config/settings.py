"""Bot settings and secrets — the target guild and the Discord token."""
import logging

from dotenv import dotenv_values

log = logging.getLogger(__name__)

TARGET_GUILD = 1426972810332340406


def check_guild(guild_id: int) -> bool:
    return guild_id == TARGET_GUILD


TOKEN = dotenv_values('.env').get('TOKEN')
if not TOKEN:
    log.error(
        "there's no token - create a .env file in this directory with "
        'TOKEN=<your bot token> (see .env.example)'
    )
