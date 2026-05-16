import asyncio
import logging
import re
import datetime

import discord
from discord import AllowedMentions

from modules import config, general
from modules.general import has_role, send, count_available, count_in_vc, emojify
from modules.role_management import RoleSession
from modules.bot_init import bot

log = logging.getLogger(__name__)

async def voice_check(rs: RoleSession, member: discord.Member) -> None:
    async def check(
        vc: str,
        vc_role: str,
        vc_leader_role: str,
        reverse_role: str,
        join_msg_id: str,
        leave_msg_id: str,
        color: str = 'g',
    ):
        channel = member.guild.get_channel(config.channels[vc])
        members = await count_in_vc(member.guild, vc)

        if member.voice and member.voice.channel == channel:
            if not has_role(member, config.roles[vc_role]):
                await send(
                    config.message(
                        join_msg_id,
                        member=member.mention,
                        count=emojify(str(members), color),
                    )
                )
            if has_role(member, config.roles['leader']):
                rs.add(config.roles[vc_leader_role])
            rs.add(config.roles[vc_role])
            rs.remove(config.roles[reverse_role])
        else:
            if has_role(member, config.roles[vc_role]):
                await send(
                    config.message(
                        leave_msg_id,
                        member=member.mention,
                        count=emojify(str(members), color),
                    )
                )
            rs.remove(config.roles[vc_role])
            rs.remove(config.roles[vc_leader_role])
            if has_role(member, config.roles['available']):
                rs.add(config.roles[reverse_role])

    await check('vc', 'in_vc', 'in_vc_leader', 'available_not_in_vc', 'join_vc_force', 'leave_vc_force')
    await check('vc2', 'in_vc_2', 'in_vc_2_leader', 'available_not_in_vc_2', 'join_vc_2_force', 'leave_vc_2_force', 'p')
    await check('vc3', 'in_vc_3', 'in_vc_3_leader', 'available_not_in_vc_3', 'join_vc_3_force', 'leave_vc_3_force', 'r')


async def add_availability(rs: RoleSession, member: discord.Member) -> None:
    if not has_role(member, config.roles['available']):
        available_people = await count_available(member.guild)
        if available_people >= 8:
            await send(
                config.message(
                    'available_ping',
                    name=member.mention,
                    available_count=emojify(str(available_people), 'b'),
                ),
                pings=AllowedMentions(users=False, roles=True),
            )
        else:
            await send(
                config.message(
                    'available',
                    name=member.mention,
                    available_count=emojify(str(available_people), 'b'),
                ),
                pings=AllowedMentions.none(),
            )

    rs.add('available')
    rs.remove('not_available')

    msg = await member.guild.get_channel(
        config.channels['availability']
    ).fetch_message(config.channels['availability_message'])

    await msg.remove_reaction(
        discord.PartialEmoji(id=config.channels['availability_reaction'], name='available'),
        member.guild.me,
    )


async def remove_availability(rs: RoleSession, member: discord.Member) -> None:
    guild = member.guild
    available_people = await count_available(guild)

    if has_role(member, config.roles['available']):
        await send(
            config.message(
                'unavailable',
                name=member.mention,
                available_count=emojify(str(available_people), 'b'),
            ),
            pings=AllowedMentions.none(),
        )

    # mark as user-initiated so on_member_update doesn't send a second message
    user_unavailable_pending.add(member.id)

    rs.remove('available')
    rs.add('not_available')

    if available_people == 0:
        msg = await member.guild.get_channel(
            config.channels['availability']
        ).fetch_message(config.channels['availability_message'])

        await msg.add_reaction(
            discord.PartialEmoji(id=config.channels['availability_reaction'], name='available')
        )


async def availability_check(rs: RoleSession, member: discord.Member) -> None:
    channel = member.guild.get_channel(config.channels['availability'])
    try:
        msg = await channel.fetch_message(config.channels['availability_message'])
    except (discord.NotFound, discord.Forbidden):
        return

    found_reaction = None
    for reaction in msg.reactions:
        if reaction.emoji.id == config.channels['availability_reaction']:
            found_reaction = reaction
            break

    if found_reaction:
        async for user in found_reaction.users():
            if user == member:
                await add_availability(rs, member)
                return
        await remove_availability(rs, member)


def check_member_join_date(member: discord.Member) -> int | None:
    if member.guild.get_role(config.roles['newbie']) not in member.roles:
        return None
    if not member.joined_at:
        return None
    now = datetime.datetime.now(member.joined_at.tzinfo)
    return (now - member.joined_at).days


async def full_check_member(rs: RoleSession, member: discord.Member) -> None:
    await availability_check(rs, member)
    await voice_check(rs, member)
    days = check_member_join_date(member)
    if days is not None and days > 7:
        rs.remove('newbie')


async def check_all_members() -> None:
    server = bot.get_guild(config.TARGET_GUILD)
    await server.chunk()
    members = server.members
    total = len(members)

    for i, member in enumerate(members, 1):
        if not member.bot:
            async with RoleSession(member) as rs:
                await full_check_member(rs, member)
        log.debug('checking members - %s%%', round(i * 100 / total, 1))

    await general.update_status(status=discord.Status.online)  # type: ignore


async def check_inactivity() -> None:
    """Standalone inactivity check used by the .check_inactive_people command."""
    await run_activity_checks()


# ---------------------------------------------------------------------------
# activity cache
# ---------------------------------------------------------------------------

last_activity_cache: dict[int, float] = {}

bot_inactive_pending: set[int] = set()
bot_unavailable_pending: set[int] = set()
user_unavailable_pending: set[int] = set()


def update_cache(member_id: int, ts: float = None) -> None:
    last_activity_cache[member_id] = ts or discord.utils.utcnow().timestamp()


async def build_activity_cache() -> None:
    """Runs once on startup to seed the cache and prevent false positives."""
    chat = bot.get_channel(config.channels['chat'])

    log.info('building activity cache...')
    async for msg in chat.history(limit=10000):
        ts = msg.created_at.timestamp()

        if not msg.author.bot:
            if ts > last_activity_cache.get(msg.author.id, 0):
                update_cache(msg.author.id, ts)
        elif msg.author == bot.user:
            if '<:join:1436503008924926052>' in msg.content:
                for user_id in (int(x) for x in re.findall(r'\d{17,19}', msg.content)):
                    if ts > last_activity_cache.get(user_id, 0):
                        update_cache(user_id, ts)

    log.info('cache built — tracked %d members.', len(last_activity_cache))


async def run_activity_checks() -> None:
    """
    Called every 45 minutes by member_checker.
    Marks members inactive if they haven't spoken in 6 days.
    Removes availability if they haven't been active in 1.5 hours.
    """
    guild = bot.get_guild(config.TARGET_GUILD)
    now = discord.utils.utcnow().timestamp()
    cutoff_6d = now - (6 * 24 * 60 * 60)
    cutoff_1h = now - (1.5 * 60 * 60)

    availability_msg = None

    for m in guild.members:
        if m.bot or (m.voice and m.voice.channel):
            continue

        last_ts = last_activity_cache.get(m.id, 0)
        needs_inactive = (
            not general.has_role(m, config.roles['inactive'])
            and not general.has_role(m, config.roles['explained_inactive'])
            and last_ts < cutoff_6d
        )
        needs_unavail = (
            general.has_role(m, config.roles['available'])
            and last_ts < cutoff_1h
        )

        if not needs_inactive and not needs_unavail:
            continue

        async with RoleSession(m) as rs:
            if needs_unavail:
                bot_unavailable_pending.add(m.id)
                if not availability_msg:
                    ch = guild.get_channel(config.channels['availability'])
                    availability_msg = await ch.fetch_message(
                        config.channels['availability_message']
                    )
                rs.remove('available')
                await availability_msg.remove_reaction(
                    discord.PartialEmoji(
                        id=config.channels['availability_reaction'],
                        name='available',
                    ),
                    m,
                )
                await general.send(
                    config.message(
                        'unavailable_auto_bot',
                        name=m.mention,
                        available_count=emojify(str(await count_available(guild)), 'b'),
                    ),
                    pings=discord.AllowedMentions.none(),
                )

            if needs_inactive:
                bot_inactive_pending.add(m.id)
                rs.add('inactive')
                rs.remove('person')

    await general.update_status()


# ---------------------------------------------------------------------------
# interested roles  (tiered reaction roles with debounce)
# ---------------------------------------------------------------------------

INTERESTED_PREFIX = '🎮 interested in '
INTERESTED_PREFIX_BASE = '🎮🟢 interested in '
INTERESTED_PREFIX_STAR = '🎮⭐ interested in '
INTERESTED_PREFIX_ULTIMATE = '🎮☄️ interested in '

INTERESTED_CHANNEL_ID = 1464608724667858975
INTERESTED_MESSAGE_BASE = 1464609114612302035
INTERESTED_MESSAGE_STAR = 1467834855315210376
INTERESTED_MESSAGE_ULTIMATE = 1467834856640745542

user_pending_changes: dict = {}
user_debounce_tasks: dict = {}
user_initial_states: dict = {}


def get_interested_role_map(guild: discord.Guild, message_id: int) -> dict:
    role_map = {}

    if message_id == INTERESTED_MESSAGE_BASE:
        prefixes = [INTERESTED_PREFIX_BASE, INTERESTED_PREFIX]
    elif message_id == INTERESTED_MESSAGE_STAR:
        prefixes = [INTERESTED_PREFIX_STAR]
    elif message_id == INTERESTED_MESSAGE_ULTIMATE:
        prefixes = [INTERESTED_PREFIX_ULTIMATE]
    else:
        return role_map

    for role in guild.roles:
        suffix = None
        for p in prefixes:
            if role.name.startswith(p):
                suffix = role.name.replace(p, '').strip().lower()
                break
        if not suffix:
            continue

        if suffix == 'miscellaneous hosts':
            role_map['🎮'] = role
            continue

        clean = ''.join(c for c in suffix if c.isalnum() or c.isspace())
        emoji = discord.utils.get(guild.emojis, name=f"badge_{clean.replace(' ', '_')}")
        if emoji:
            role_map[str(emoji)] = role

    return role_map


async def process_interested_changes(user_id: int, guild: discord.Guild) -> None:
    if user_id not in user_pending_changes:
        return

    changes = user_pending_changes.pop(user_id)
    initial = user_initial_states.pop(user_id, set())

    final_roles = (initial | changes['added']) - changes['removed']
    net_added = final_roles - initial
    net_removed = initial - final_roles

    member = guild.get_member(user_id)
    if not member or (not net_added and not net_removed):
        return

    async with RoleSession(member) as rs:
        for role in net_added:
            rs.add(role.id)
        for role in net_removed:
            rs.remove(role.id)

    def format_names(roles: set) -> str:
        names = [f"**{r.name.split('interested in ')[-1]}**" for r in roles]
        if len(names) > 1:
            return f"{', '.join(names[:-1])} and {names[-1]}"
        return names[0]

    lines = []
    if net_removed:
        lines.append(
            f'<:no_multiplayer:1463357263811973303> {member.mention} is no longer interested in {format_names(net_removed)}'
        )
    if net_added:
        lines.append(
            f'<:yes_multiplayer:1463357364110495754> {member.mention} is now interested in {format_names(net_added)}'
        )

    if lines:
        await general.send('\n'.join(lines), pings=AllowedMentions.none())


async def schedule_interested_debounce(user_id: int, guild: discord.Guild) -> None:
    if user_id in user_debounce_tasks:
        user_debounce_tasks[user_id].cancel()

    async def _wait():
        await asyncio.sleep(7)
        await process_interested_changes(user_id, guild)
        user_debounce_tasks.pop(user_id, None)

    user_debounce_tasks[user_id] = asyncio.create_task(_wait())


async def sync_interested_reactions() -> None:
    guild = bot.get_guild(config.TARGET_GUILD)
    channel = guild.get_channel(INTERESTED_CHANNEL_ID)
    if not channel:
        return

    for mid in [INTERESTED_MESSAGE_BASE, INTERESTED_MESSAGE_STAR, INTERESTED_MESSAGE_ULTIMATE]:
        try:
            msg = await channel.fetch_message(mid)
            role_map = get_interested_role_map(guild, mid)
            sorted_emojis = sorted(
                role_map.keys(),
                key=lambda e: role_map[e].position,
                reverse=True,
            )
            existing = [str(r.emoji) for r in msg.reactions if r.me]
            for emoji_str in sorted_emojis:
                if emoji_str not in existing:
                    await msg.add_reaction(emoji_str)
        except Exception:
            log.warning('sync error for %s', mid, exc_info=True)
