import datetime
import logging

import discord
from modules import config
from modules.role_management import RoleSession

log = logging.getLogger(__name__)


def get_timeout_duration(duration: str) -> datetime.timedelta:
    timeout_duration: datetime.timedelta
    if duration.endswith('s'):
        seconds = int(duration[:-1])
        timeout_duration = datetime.timedelta(seconds=seconds)
    elif duration.endswith('m'):
        minutes = int(duration[:-1])
        timeout_duration = datetime.timedelta(minutes=minutes)
    elif duration.endswith('h'):
        hours = int(duration[:-1])
        timeout_duration = datetime.timedelta(hours=hours)
    elif duration.endswith('d'):
        days = int(duration[:-1])
        timeout_duration = datetime.timedelta(days=days)
    elif duration.endswith('w'):
        weeks = int(duration[:-1])
        timeout_duration = datetime.timedelta(weeks=weeks)
    elif duration == 'max':
        timeout_duration = datetime.timedelta(days=28)
    else:
        raise ValueError("wrong duration format you moron")

    if not timeout_duration:
        raise ValueError("wrong duration format you moron")

    if timeout_duration > datetime.timedelta(days=28):
        raise ValueError("you can't mute for more than 28 days because discord is a moron sorry")

    return timeout_duration

def format_timedelta(timedelta: datetime.timedelta) -> str:
    parts = []
    if timedelta.days > 0:
        parts.append(f"{timedelta.days} day{'s' if timedelta.days != 1 else ''}")
    seconds_total = timedelta.seconds
    hours, seconds_total = divmod(seconds_total, 3600)
    minutes, seconds = divmod(seconds_total, 60)
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} min")
    if seconds > 0:
        parts.append(f"{seconds} sec")

    formatted_timedelta = ", ".join(parts) if parts else "0 sec"
    return formatted_timedelta


async def unmute(ctx, member: discord.Member, reason: str = None):
    await member.timeout(None, reason=reason) # Setting duration to None removes timeout
    await ctx.send(f"unmuted :white_check_mark:")
    log.info('unmuted %s (ID: %s) by %s for: %s', member.display_name, member.id, ctx.author.display_name, reason)


async def warn(ctx, member: discord.Member, reason: str = None):
    async with RoleSession(member) as rs:
        if member.guild.get_role(config.roles['warn_1']) in member.roles:
            #timeout_duration = datetime.timedelta(days=3)
            #await member.timeout(timeout_duration, reason=reason)
            rs.add(config.roles['warn_2'])
            rs.remove(config.roles['warn_1'])
            await ctx.send(f"warned the guy :white_check_mark:\nwarn 2/3")

        elif member.guild.get_role(config.roles['warn_2']) in member.roles:
            #timeout_duration = datetime.timedelta(days=7)
            #await member.timeout(timeout_duration, reason=reason)
            rs.add(config.roles['warn_3'])
            rs.remove(config.roles['warn_2'])
            await ctx.send(f"warned the guy :white_check_mark:\nwarn 3/3\nnext warn will autoban them btw")

        elif member.guild.get_role(config.roles['warn_3']) in member.roles:
            await member.ban()

        else:
            #timeout_duration = datetime.timedelta(days=1)
            rs.add(config.roles['warn_1'])
            #await member.timeout(timeout_duration, reason=reason)
            await ctx.send(f"warned the guy :white_check_mark:\nwarn 1/3")
