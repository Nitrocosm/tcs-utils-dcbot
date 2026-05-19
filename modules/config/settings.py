"""Bot settings and secrets — the target guild and the Discord token."""
import logging
import os

from dotenv import dotenv_values

log = logging.getLogger(__name__)

# Default production guild. Override with TARGET_GUILD in .env to point at a
# staging/test guild without editing this file.
_DEFAULT_TARGET_GUILD = 1426972810332340406
_env = dotenv_values('.env')
TARGET_GUILD = int(_env.get('TARGET_GUILD') or os.getenv('TARGET_GUILD') or _DEFAULT_TARGET_GUILD)


def check_guild(guild_id: int) -> bool:
    return guild_id == TARGET_GUILD


TOKEN = _env.get('TOKEN') or os.getenv('TOKEN')
if not TOKEN:
    log.error(
        "there's no token - create a .env file in this directory with "
        'TOKEN=<your bot token> (see .env.example)'
    )
