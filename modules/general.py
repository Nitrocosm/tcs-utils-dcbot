import asyncio
import functools
import logging

import discord
from discord import Guild
from discord.ext import commands
from modules import config
from modules.bot_init import bot

log = logging.getLogger(__name__)


async def send(msg: str, where: str = 'chat', pings: discord.AllowedMentions = None) -> discord.Message:
    channel = bot.get_channel(config.channels[where])
    if channel is None:
        log.error("channel %r (id=%s) not available", where, config.channels.get(where))
        raise RuntimeError(f"channel {where!r} not available")
    sent = await channel.send(msg, allowed_mentions=pings)
    await update_status()
    return sent

async def timed_delete_msg(msg: discord.Message, text: str, duration: int = 10):
    for i in range(1, duration):
        if i <= 11:
            await msg.edit(content=f':clock{duration-i}: {text}')
            await asyncio.sleep(1)
        else:
            await msg.edit(content=f':white_check_mark: {text}')
            await asyncio.sleep(1)
    await msg.delete()

async def send_timed_delete_msg(text: str, duration: int = 10, where: str = 'chat') -> None:
    msg = await send(text, where=where)
    await timed_delete_msg(msg, text, duration)



async def count_filtered_members(guild: Guild) -> int:
    excluded_role_id = config.roles['alts']
    excluded_role = guild.get_role(excluded_role_id)

    if excluded_role is None:
        log.warning('role id %s not found', excluded_role_id)

    member_count = 0
    for member in guild.members:
        if member.bot:
            continue
        if excluded_role and excluded_role in member.roles:
            continue
        member_count += 1
    return member_count

def matches_availability_emoji(emoji) -> bool:
    """True if ``emoji`` is the configured availability reaction emoji.

    Works whether the configured value is a custom-emoji snowflake id (int,
    matches ``Emoji``/``PartialEmoji`` by ``.id``) or a Unicode glyph (str,
    matches ``str`` reactions directly). Returns False when the config value
    is the staging sentinel (``0`` or empty)."""
    expected = config.channels['availability_reaction']
    if not expected:
        return False
    if isinstance(emoji, str):
        return emoji == expected
    return getattr(emoji, 'id', None) == expected


async def count_available(guild: discord.Guild) -> int:
    channel = guild.get_channel(config.channels['availability'])
    try:
        msg = await channel.fetch_message(config.channels['availability_message'])
    except (discord.NotFound, discord.Forbidden):
        return 0
    found_reaction: discord.Reaction | None = None
    for reaction in msg.reactions:
        if matches_availability_emoji(reaction.emoji):
            found_reaction = reaction
            break
    if not found_reaction:
        return 0
    count = found_reaction.count
    if found_reaction.me:
        count -= 1
    return count


async def count_in_vc(guild: discord.Guild, vc: str = 'vc') -> int:
    channel = guild.get_channel(config.channels[vc])
    if not channel:
        return 0
    return len(channel.members)

async def set_status(text: str, *, status: discord.Status = None) -> None:
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=text), status=status)


async def get_status_text(guild: discord.Guild) -> str:
    vc_count = await count_in_vc(guild, 'vc')
    vc_2_count = await count_in_vc(guild, 'vc2')
    vc_3_count = await count_in_vc(guild, 'vc3')
    available_count = await count_available(guild)
    members = await count_filtered_members(guild)

    text_members = f'{members} 👥'

    text_in_vc = ''
    if vc_count or vc_2_count or vc_3_count:
        text_in_vc = ' / vc'
        if vc_count:
            text_in_vc += f' - {vc_count} 🟢'
        if vc_2_count:
            text_in_vc += f' - {vc_2_count} 🟣'
        if vc_3_count:
            text_in_vc += f' - {vc_3_count} 🔴'

    text_available = ''
    if available_count:
        if vc_count or vc_2_count or vc_3_count:
            text_available = f' / {available_count} av.'
        else:
            text_available = f' / {available_count} available'

    return f'{text_members}{text_available}{text_in_vc}'


async def update_status(status: discord.Status = None) -> None:
    guild = bot.get_guild(config.TARGET_GUILD)
    if not guild:
        return
    status_text = await get_status_text(guild)
    await set_status(status_text, status=status)


def has_role(member: discord.Member, role_id: int) -> bool:
    role = member.guild.get_role(role_id)
    if not role or role not in member.roles:
        return False
    return True

def has_role_object(member: discord.Member, role: discord.Role) -> bool:
    if not role or role not in member.roles:
        return False
    return True



def emojify(text: str, color: str = '') -> str:
    converted_text = ''
    for char in text:
        converted_text += config.emoji[f'{char}{color}']
    return "".join(converted_text)


def _find_ctx(args: tuple) -> commands.Context:
    """Locate the commands.Context in a command call's positional args.

    Works whether the decorated callable is a module-level command (called as
    ``(ctx, ...)``) or a Cog method (called as ``(self, ctx, ...)``).
    """
    for a in args:
        if isinstance(a, commands.Context):
            return a
    raise RuntimeError('no Context found in command call args')


def has_perms(required_perm: str):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            ctx = _find_ctx(args)
            if required_perm == 'owner':
                if ctx.author.id != ctx.guild.owner_id:
                    return await ctx.send(config.message("nuh_uh"))
            else:
                author_perms = ctx.author.guild_permissions
                if not getattr(author_perms, required_perm, False):
                    return await ctx.send(config.message("nuh_uh"))

            return await func(*args, **kwargs)
        return wrapper
    return decorator


def can_moderate_member(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        ctx = _find_ctx(args)
        # ``member`` is the positional arg right after ctx, or in kwargs.
        ctx_index = args.index(ctx)
        member = args[ctx_index + 1] if ctx_index + 1 < len(args) else kwargs.get('member')

        if not member:
            await ctx.send(config.message("bot_doesnt_have_perms"))
            return await ctx.send(f'<@{config.OWNER_ID}> fix ur fucking bot\n'
                                  'you added a @can_moderate_member decorator where you shouldn\'t have dumbass\n'
                                  '-# [can_moderate_member expects a member in the command args, no member arg found]')
        if member == ctx.author:
            return await ctx.send(config.message("nuh_uh"))
        if member == ctx.guild.me:
            return await ctx.send(config.message("nuh_uh"))
        if ctx.author.top_role <= member.top_role and ctx.author.id != ctx.guild.owner_id:
            return await ctx.send(config.message("nuh_uh"))
        return await func(*args, **kwargs)
    return wrapper


def try_bot_perms(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        ctx = _find_ctx(args)
        try:
            await func(*args, **kwargs)
        except discord.Forbidden as e:
            await ctx.send(config.message("bot_doesnt_have_perms"))
            await ctx.send(f'<@{config.OWNER_ID}> fix ur fucking bot\n```{e}```')
            raise e
        except Exception as e:
            await ctx.send(config.message("bot_doesnt_have_perms"))
            log.exception('error in try_bot_perms')
            await ctx.send(f'<@{config.OWNER_ID}> fix ur fucking bot\n```{e}```')
            raise e
    return wrapper




async def get_replied_message(ctx):
    ref = ctx.message.reference
    if not ref or not ref.message_id:
        return None  # not a reply

    msg = ref.resolved  # may already be cached and ready
    if isinstance(msg, discord.Message):
        return msg

    # fallback: fetch from the API
    try:
        return await ctx.channel.fetch_message(ref.message_id)
    except discord.NotFound:
        return None
    except discord.Forbidden:
        return None
    except discord.HTTPException:
        return None

def inject_reply(func):
    @functools.wraps(func)
    async def wrapper(ctx, *args, **kwargs):
        if not args and ctx.message.reference:
            ref = ctx.message.reference
            msg = ref.resolved

            if not isinstance(msg, discord.Message):
                try:
                    msg = await ctx.channel.fetch_message(ref.message_id)
                except (discord.NotFound, discord.HTTPException, discord.Forbidden):
                    msg = None

            if msg and isinstance(msg.author, discord.Member):
                return await func(ctx, msg.author, *args, **kwargs)

        return await func(ctx, *args, **kwargs)

    return wrapper
