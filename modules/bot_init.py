import discord
from discord.ext import commands

_intents = discord.Intents.default()
_intents.members = True
_intents.presences = True
_intents.reactions = True
_intents.guilds = True
_intents.message_content = True


bot = commands.Bot(command_prefix='.', intents=_intents, enable_debug_events=True, help_command=None)