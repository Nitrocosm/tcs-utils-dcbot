"""ActivityCog — voice channel & reaction events, member activity checks."""
import logging

import discord
from discord.ext import commands

from modules import activity, config, general
from modules.general import send_timed_delete_msg
from modules.role_management import RoleSession

log = logging.getLogger(__name__)


class ActivityCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── events ──────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not config.check_guild(member.guild.id) or member.bot:
            return

        activity.update_cache(member.id)

        vc1 = member.guild.get_channel(config.channels['vc'])
        vc2 = member.guild.get_channel(config.channels['vc2'])
        vc3 = member.guild.get_channel(config.channels['vc3'])

        channel_info = {
            vc1: {
                'in_vc': 'in_vc',
                'join_msg': 'join_vc',
                'leave_msg': 'leave_vc',
                'color': 'g',
            },
            vc2: {
                'in_vc': 'in_vc_2',
                'join_msg': 'join_vc_2',
                'leave_msg': 'leave_vc_2',
                'color': 'p',
            },
            vc3: {
                'in_vc': 'in_vc_3',
                'join_msg': 'join_vc_3',
                'leave_msg': 'leave_vc_3',
                'color': 'r',
            },
        }

        messages = []

        async with RoleSession(member) as rs:
            # leaving
            if before.channel in channel_info and before.channel != after.channel:
                info = channel_info[before.channel]
                messages.append(config.message(
                    info['leave_msg'],
                    member=member.mention,
                    count=general.emojify(
                        str(len(before.channel.members)),
                        info['color'],
                    ),
                ))
                rs.remove(info['in_vc'])

            # joining
            if after.channel in channel_info and before.channel != after.channel:
                info = channel_info[after.channel]
                messages.append(config.message(
                    info['join_msg'],
                    member=member.mention,
                    count=general.emojify(
                        str(len(after.channel.members)),
                        info['color'],
                    ),
                ))
                rs.add(info['in_vc'])

        if messages:
            await member.guild.get_channel(
                config.channels['chat']
            ).send(
                '\n'.join(messages),
                allowed_mentions=discord.AllowedMentions.none(),
            )

        await general.update_status(self.bot)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.bot.user.id:
            return
        activity.update_cache(payload.user_id)
        guild = self.bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return

        async with RoleSession(member) as rs:
            # availability logic
            if payload.message_id == config.channels['availability_message']:
                if payload.emoji.id == config.channels['availability_reaction']:
                    await activity.add_availability(rs, member)

            # interested roles logic (tiered) - don't commit immediately
            interested_msgs = [
                activity.INTERESTED_MESSAGE_BASE,
                activity.INTERESTED_MESSAGE_STAR,
                activity.INTERESTED_MESSAGE_ULTIMATE,
            ]
            if payload.message_id in interested_msgs:
                role_map = activity.get_interested_role_map(guild, payload.message_id)
                emoji_str = str(payload.emoji)
                if emoji_str in role_map:
                    role = role_map[emoji_str]

                    # track initial state if first change
                    if payload.user_id not in activity.user_initial_states:
                        activity.user_initial_states[payload.user_id] = {
                            r for r in role_map.values() if r in member.roles
                        }

                    # update debounce state
                    state = activity.user_pending_changes.setdefault(
                        payload.user_id, {'added': set(), 'removed': set()}
                    )
                    state['added'].add(role)
                    state['removed'].discard(role)
                    await activity.schedule_interested_debounce(payload.user_id, guild)
                    return  # don't commit yet

            # static reaction roles
            if payload.message_id in config.REACTION_ROLES:
                emoji_str = str(payload.emoji)
                if emoji_str in config.REACTION_ROLES[payload.message_id]:
                    rs.add(config.REACTION_ROLES[payload.message_id][emoji_str])

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if payload.user_id == self.bot.user.id:
            return
        activity.update_cache(payload.user_id)
        guild = self.bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return

        async with RoleSession(member) as rs:
            # availability logic
            if payload.message_id == config.channels['availability_message']:
                if payload.emoji.id == config.channels['availability_reaction']:
                    await activity.remove_availability(rs, member)

            # interested roles logic (tiered) - don't commit immediately
            interested_msgs = [
                activity.INTERESTED_MESSAGE_BASE,
                activity.INTERESTED_MESSAGE_STAR,
                activity.INTERESTED_MESSAGE_ULTIMATE,
            ]
            if payload.message_id in interested_msgs:
                role_map = activity.get_interested_role_map(guild, payload.message_id)
                emoji_str = str(payload.emoji)
                if emoji_str in role_map:
                    role = role_map[emoji_str]

                    # track initial state if first change
                    if payload.user_id not in activity.user_initial_states:
                        activity.user_initial_states[payload.user_id] = {
                            r for r in role_map.values() if r in member.roles
                        }

                    # update debounce state
                    state = activity.user_pending_changes.setdefault(
                        payload.user_id, {'added': set(), 'removed': set()}
                    )
                    state['removed'].add(role)
                    state['added'].discard(role)
                    await activity.schedule_interested_debounce(payload.user_id, guild)
                    return  # don't commit yet

            # static reaction roles
            if payload.message_id in config.REACTION_ROLES:
                emoji_str = str(payload.emoji)
                if emoji_str in config.REACTION_ROLES[payload.message_id]:
                    rs.remove(config.REACTION_ROLES[payload.message_id][emoji_str])

    # ── helpers ─────────────────────────────────────────────────────────────

    async def _remove_availability_auto(self, member):
        """Currently unused. Preserved verbatim from pre-refactor main.py for
        parity; only referenced in a commented-out line inside `unavailable`.
        """
        channel = self.bot.get_channel(config.channels['availability'])
        msg = await channel.fetch_message(config.channels['availability_message'])
        reaction_flag = False
        for reaction in msg.reactions:
            if reaction.emoji == discord.PartialEmoji(id=config.channels['availability_reaction'], name='available'):
                async for user in reaction.users():
                    if user == member:
                        reaction_flag = True
                        break

        async with RoleSession(member) as rs:
            rs.remove(config.roles['available'])
        if reaction_flag:
            await msg.remove_reaction(
                discord.PartialEmoji(id=config.channels['availability_reaction'], name='available'), member)
            await general.send(
                config.message(
                    'unavailable_auto',
                    name=member.mention,
                    available_count=f"{general.emojify(str(await activity.count_available(self.bot)), 'b')}",
                ),
                pings=discord.AllowedMentions.none(),
            )

    # ── commands ────────────────────────────────────────────────────────────

    @commands.command()
    @general.try_bot_perms
    @general.has_perms('manage_roles')
    async def check(self, ctx, member: discord.Member):
        async with RoleSession(member) as rs:
            await activity.full_check_member(rs, member)
            await send_timed_delete_msg(f'checked {member.display_name}')

    @commands.command()
    @general.try_bot_perms
    @general.has_perms('manage_roles')
    async def check_inactive_people(self, ctx):
        await activity.check_inactivity()

    @commands.command()
    @general.try_bot_perms
    @general.has_perms('manage_roles')
    async def unavailable(self, ctx, member: discord.Member):
        # await self._remove_availability_auto(member)
        async with RoleSession(member) as rs:
            rs.remove(config.roles['available'])


async def setup(bot: commands.Bot):
    await bot.add_cog(ActivityCog(bot))
