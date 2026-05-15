"""ServerEventsCog — server lifecycle, audit log, and message events.

Handles member join/leave/update announcements, audit-log voice-channel
status edits, raw gateway join-application events, DM forwarding to mod
chat, mod-chat reply forwarding, easter eggs, and the roleplay
"kill"/"hug"/etc. shortcuts.

Does NOT call ``bot.process_commands`` in its ``on_message`` listener: as
a Cog listener it is additive, and discord.py's default ``on_message``
still runs and dispatches commands. Calling it here would double-fire
every command.
"""
import json
import logging
import re

import discord
from discord import VoiceChannel
from discord.ext import commands

from modules import activity, badges, config, general
from modules.config import TARGET_GUILD
from modules.points import (
    calculate_points,
    get_member_rank,
    has_all_challenges,
    parse_challenge_role,
    update_leaderboard_message,
)
from modules.role_management import RoleSession

log = logging.getLogger(__name__)


# ── module-level helpers (called from on_socket_raw_receive) ────────────────


async def _on_join_request_create(payload: dict):
    """Fires when someone submits a join application (status: PENDING)."""
    user = payload.get("user", {})
    user_id = user.get("id")
    username = user.get("global_name") or user.get("username", "unknown")
    request_id = payload.get("id")

    # await general.send(
    #     f'<:application_add:1501552015816527963> <@{user_id}> ({username}) sent a join application',
    #     'mod_chat'
    # )
    await general.send(
        '<:application_add:1501552015816527963> we got a new join application!',
        'mod_chat',
    )


async def _on_join_request_delete(payload: dict):
    """
    Fires when an application is rejected or withdrawn.
    If actioned_by_user is present and isn't the applicant, it was a mod rejection.
    Otherwise, the applicant likely withdrew themself.
    """
    user_id = payload.get("user_id")
    request_id = payload.get("id")
    actioned_by = payload.get("actioned_by_user") or {}
    actioned_by_id = actioned_by.get("id")

    if actioned_by_id and actioned_by_id != user_id:
        await general.send(
            f'<:application_reject:1501552028512555039> <@{actioned_by_id}> rejected <@{user_id}>\'s application\n',
            'mod_chat',
        )
    else:
        await general.send(
            f'<:application_reject:1501552028512555039> <@{user_id}> withdrew their application\n',
            'mod_chat',
        )


class ServerEventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── member updates (challenge roles, promotions, name change) ───────────

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if before.roles != after.roles:
            async with RoleSession(after) as rs:
                before_roles = set(before.roles)
                after_roles = set(after.roles)
                added_roles = after_roles - before_roles
                removed_roles = before_roles - after_roles

                # track old rank before any leaderboard update
                old_rank = get_member_rank(after.guild, before)
                challenge_changed = False

                log_thread = after.guild.get_thread(config.channels['challenge_log_thread'])

                for role in added_roles:
                    role_info = parse_challenge_role(role)
                    if role_info:
                        challenge_changed = True

                        emoji = badges.get_challenge_emoji(
                            after.guild, role_info['name'], role_info['points']
                        )
                        announce = 'completed a custom challenge' if not role.name.startswith('🏆') else 'completed'
                        await general.send(
                            f'{emoji} {after.mention} {announce} **{role_info["name"]}** ({role_info["points"]} pts)')

                        new_rank = get_member_rank(after.guild, after)
                        current_pts = calculate_points(after)[0]
                        log_msg = (
                            f"{emoji} {after.mention} got **{role_info['name']}** [`"
                            f"+{role_info['points']} pts`] - `{current_pts} pts` total; #{new_rank} on leaderboard"
                        )
                        if log_thread:
                            await log_thread.send(log_msg, allowed_mentions=discord.AllowedMentions.none())

                for role in removed_roles:
                    role_info = parse_challenge_role(role)
                    if role_info:
                        challenge_changed = True
                        if old_rank is None:
                            old_rank = get_member_rank(after.guild, after)

                        announce = '(custom challenge) ' if not role.name.startswith('🏆') else ''
                        await general.send(
                            f'<:no:1454950318042255410> {after.mention}\'s **{role_info["name"]}** {announce}completion was taken')

                        new_rank = get_member_rank(after.guild, after)
                        current_pts = calculate_points(after)[0]
                        log_msg = (
                            f"<:no:1454950318042255410> {after.mention}'s completion of **{role_info['name']}** was revoked [`"
                            f"-{role_info['points']} pts`] - `{current_pts} pts` total; #{new_rank} on leaderboard"
                        )
                        if log_thread:
                            await log_thread.send(log_msg, allowed_mentions=discord.AllowedMentions.none())

                # update leaderboard and check for rank changes
                if challenge_changed:
                    await update_leaderboard_message(self.bot, after.guild)
                    new_rank = get_member_rank(after.guild, after)

                    # if old_rank != new_rank and new_rank is not None:
                    #     emoji = LB_EMOJI.get(new_rank, "🏆")
                    #     await general.send(
                    #         f"{emoji} {after.mention}'s leaderboard position is now **#{new_rank}**!"
                    #     )

                # check completion roles
                had_all_base = after.guild.get_role(config.roles["completion_all_base"]) in after_roles
                has_all_base = has_all_challenges(after, {"🟢"})

                if has_all_base and not had_all_base:
                    rs.add(config.roles["completion_all_base"])
                    await general.send(
                        f"{config.emoji['star_completion']} {after.mention} beat **all base challenges**!"
                    )

                had_all_ultimate = after.guild.get_role(config.roles["completion_all_ultimate"]) in after_roles
                has_all_ultimate = has_all_challenges(after, {"⭐", "☄"})

                if has_all_ultimate and not had_all_ultimate:
                    rs.add(config.roles["completion_all_ultimate"])
                    await general.send(
                        f"{config.emoji['star_pure_completion']} {after.mention} beat **all ultimate challenges**!"
                    )

                for role in added_roles:
                    if role.id == config.roles['mod']:
                        await general.send(config.message('promotion', mention=after.mention))
                        await general.send(config.message('promotion_welcome', mention=after.mention), 'mod_chat')
                    elif role.id == config.roles['leader']:
                        await general.send(config.message('new_leader', mention=after.mention))
                        await general.send(config.message('new_leader', mention=after.mention), 'leader_chat')
                    elif role.id == config.roles['inactive']:
                        if after.id in activity.bot_inactive_pending:
                            activity.bot_inactive_pending.discard(after.id)
                            # message already sent by run_activity_checks
                        else:
                            await general.send(config.message('inactive_mods', mention=after.mention))
                    elif role.id == config.roles['explained_inactive']:
                        await general.send(config.message('explained_inactive', mention=after.mention))
                    elif role.id == config.roles['spoiler']:
                        await general.send(config.message('spoiler_add', mention=after.mention), 'spoiler')

                for role in removed_roles:
                    if role.id == config.roles['mod']:
                        await general.send(config.message('demotion', mention=after.mention))
                        await general.send(config.message('demotion_goodbye', mention=after.mention), 'mod_chat')
                    elif role.id == config.roles['leader']:
                        await general.send(config.message('leader_removed', mention=after.mention))
                        await general.send(config.message('leader_removed', mention=after.mention), 'leader_chat')
                    elif role.id == config.roles['newbie']:
                        await general.send(config.message('newbie', mention=after.mention))
                    elif role.id == config.roles['inactive']:
                        await general.send(config.message('inactive_revoke', mention=after.mention))
                    elif role.id == config.roles['spoiler']:
                        await general.send(config.message('spoiler_remove', mention=after.mention), 'spoiler')
                    elif role.id == config.roles['available']:
                        if after.id in activity.bot_unavailable_pending:
                            activity.bot_unavailable_pending.discard(after.id)
                            # message already sent by run_activity_checks
                        elif after.id in activity.user_unavailable_pending:
                            activity.user_unavailable_pending.discard(after.id)
                            # message already sent by remove_availability
                        else:
                            # moderator manually removed the role
                            available_people = await general.count_available(after.guild)
                            await general.send(
                                config.message(
                                    'unavailable_auto',
                                    name=after.mention,
                                    available_count=general.emojify(str(available_people), 'b'),
                                ),
                                pings=discord.AllowedMentions.none(),
                            )

        if before.nick != after.nick:
            old = before.nick if before.nick else before.display_name
            new = after.nick if after.nick else after.display_name
            await general.send(config.message('name_change', mention=after.mention, old_name=old, new_name=new))
            await general.send(
                f':information_source:{config.message("name_change", mention=after.mention, old_name=old, new_name=new)}',
                'mod_chat',
            )

    # ── join / leave / kick / ban ───────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        if not config.check_guild(guild.id):
            return

        async with RoleSession(member) as rs:
            if member.bot:
                await general.send(config.message('join_bot', mention=member.mention))
                rs.add('bot')
            else:
                await general.send(config.message('join', mention=member.mention))
                await general.send(msg='-# **read below for just a quick tour around :3**\n'
                                        '-# - please read <#1442604555798974485> and <#1426974985402187776>! they\'re very important!\n'
                                        '-# - grab some <#1464608724667858975> to get pinged when someone wants to play a challenge\n'
                                        '-# - grab <#1434653852367585300> when you are ready to play! (don\'t forget to remove it when you stop being available!)\n'
                                        '-# - read some of the challenge channels to get started! complete challenges to get points to get higher on the <#1456353494448734331>\n'
                                        '-# - to get the private server link, simply say "ps" in any channel, the bot will send it\n'
                                        '-# - please respect others and remain active! unexplained long inactivity is something very frowned upon here')
                await general.send(f':information_source:<:join:1436503008924926052> {member.mention} ({member.display_name}) joined the server\n-# reminder to set their nickname to roblox display name', 'mod_chat')

                for role in config.roles['new_people']:
                    rs.add(role)

        activity.update_cache(member.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        if not config.check_guild(guild.id):
            return

        if member.bot:
            await general.send(config.message('kick_bot', mention=member.mention))

        else:
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
                if entry.target == member and \
                    (discord.utils.utcnow() - entry.created_at).total_seconds() < 5:
                        await general.send(config.message('kick', mention=member.mention, display=member.nick))
                        await general.send(
                            f':information_source:<:kick:1439803052826689537> {member.mention} ({member.display_name}) got kicked',
                            'mod_chat')
                        return

            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
                if entry.target == member and \
                    (discord.utils.utcnow() - entry.created_at).total_seconds() < 5:
                        await general.send(config.message('ban', mention=member.mention, display=member.nick))
                        await general.send(
                            f':information_source:<:ban:1438882547588141118> {member.mention} ({member.display_name}) got banned',
                            'mod_chat')
                        return

            await general.send(config.message('leave', mention=member.mention, display=member.nick))
            await general.send(
                f':information_source:<:leave:1436503027937841173> {member.mention} ({member.display_name}) left the server',
                'mod_chat')

    # ── raw socket: undocumented join-application events ───────────────────

    @commands.Cog.listener()
    async def on_socket_raw_receive(self, msg: str):
        try:
            data = json.loads(msg)
        except (json.JSONDecodeError, TypeError):
            return

        if data.get("op") != 0:
            return

        event_type = data.get("t")
        payload = data.get("d", {})

        # ignore events from other guilds
        guild_id = payload.get("guild_id")
        if guild_id and int(guild_id) != TARGET_GUILD:
            return

        if event_type == "GUILD_JOIN_REQUEST_CREATE":
            await _on_join_request_create(payload)
        # elif event_type == "GUILD_JOIN_REQUEST_DELETE":
        #     await _on_join_request_delete(payload)

    # ── messages: DMs, easter eggs, RP shortcuts ────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author == self.bot.user:
            return

        if not message.guild:
            await general.send(f'***DM FROM {message.author.mention}** ({message.author.display_name})**:***\n\n{message.content}\n\n*replies to this message are automatically forwarded to the sender*', 'mod_chat')
            await message.channel.send('*your message has been forwarded to mod chat*')

        if message.guild.id == TARGET_GUILD:
            activity.update_cache(message.author.id)

            if message.content.lower() == 'ps':     # '<#1426974154556702720>' in message.content or
                await message.channel.send(
                    'link: **https://www.roblox.com/share?code=1141897d2bd9a14e955091d8a4061ee5&type=Server**',
                    suppress_embeds=True)

            if message.channel == self.bot.get_channel(config.channels['mod_chat']) and message.reference and isinstance(message.reference.resolved, discord.Message):
                pattern = r'<@.+>'
                match = re.match(pattern, message.reference.resolved.content)
                if match:
                    member_id = int(match.group(1)[2:][:-1])
                    member = self.bot.get_user(member_id)
                    await member.send(f'***a mod responded:***\n\n{message.content}')
                    await message.channel.send(f'*your message has been forwarded to {member.mention}*')

            if 'one more' in message.content.lower():
                await message.channel.send(
                    'https://cdn.discordapp.com/attachments/1426972811293098014/1438983499804708915/image.png?ex=6941bbd1&is=69406a51&hm=eb4a1cd864b53f8c9865afd49aec5dd6a54fed7c327bd262df17b69589bef0bb&'
                )

            if 'npc' == message.content.lower():
                await message.reply('yep thats me', allowed_mentions=discord.AllowedMentions.none())

            if 'bot' == message.content.lower():
                await message.reply('online :white_check_mark:', allowed_mentions=discord.AllowedMentions.none())

            if not self.bot.pings:
                if isinstance(message.author, discord.Member):
                    if f'<@{config.OWNER_ID}>' in message.content:
                        await message.reply(
                            "*note: lostya marked themself temporarily unavailable. they will come back to the ping later.*\n"
                            "*in the meanwhile, try pinging one of the other available mods instead.*\n"
                            "-# *please do not delete your message. it is better if they come back and see the ping's source, instead of wondering where the ghost ping came from.*"
                        )

            # roleplay actions
            rp_actions = {
                'kill': 'rp_kill',
                'hug': 'rp_hug',
                'kiss': 'rp_kiss',
                'high five': 'rp_high_five',
                'highfive': 'rp_high_five',
                'shake hands': 'rp_handshake',
                'handshake': 'rp_handshake',
                'burn': 'rp_burn',
                'punch': 'rp_punch',
                'slap': 'rp_slap',
                'pat': 'rp_pat',
                'touch': 'rp_touch',
            }

            content_lower = message.content.lower().strip()
            target = None
            action = None

            # check if replying with just the action word
            if message.reference and message.reference.resolved:
                replied_msg = message.reference.resolved
                if isinstance(replied_msg.author, discord.Member):
                    for action_word, action_key in rp_actions.items():
                        if content_lower == action_word:
                            action = action_key
                            target = replied_msg.author
                            break

            # check for "action @member" pattern
            if not action:
                for action_word, action_key in rp_actions.items():
                    pattern = rf'^{re.escape(action_word)}\s+<@!?(\d+)>$'
                    match = re.match(pattern, content_lower)
                    if match:
                        member_id = int(match.group(1))
                        member = message.guild.get_member(member_id)
                        if member:
                            action = action_key
                            target = member
                            break

            if action and target:
                response = config.message(action, author=message.author.mention, target=target.mention)
                await message.channel.send(response)

        # NOTE: do NOT call `bot.process_commands` here. As a Cog listener this
        # handler is additive; discord.py's default on_message still runs and
        # dispatches commands. Calling it would double-fire every command.

    # ── audit log: VC status changes ────────────────────────────────────────

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry):
        if entry.action.value == 192:
            vc: VoiceChannel = self.bot.get_channel(config.channels['vc'])
            vc2 = self.bot.get_channel(config.channels['vc2'])
            vc3 = self.bot.get_channel(config.channels['vc3'])

            new_status = None

            if self.bot.get_channel(entry._target_id) == vc:
                # new_status = vc.status
                if new_status:
                    await general.send(config.message('edit_vc', member=entry.user.mention, status=new_status), pings=discord.AllowedMentions.none())
                else:
                    await general.send(config.message('edit_vc_no_status', member=entry.user.mention), pings=discord.AllowedMentions.none())
            elif self.bot.get_channel(entry._target_id) == vc2:
                if new_status:
                    await general.send(config.message('edit_vc_2', member=entry.user.mention, status=new_status), pings=discord.AllowedMentions.none())
                else:
                    await general.send(config.message('edit_vc_2_no_status', member=entry.user.mention), pings=discord.AllowedMentions.none())
            elif self.bot.get_channel(entry._target_id) == vc3:
                if new_status:
                    await general.send(config.message('edit_vc_3', member=entry.user.mention, status=new_status), pings=discord.AllowedMentions.none())
                else:
                    await general.send(config.message('edit_vc_3_no_status', member=entry.user.mention), pings=discord.AllowedMentions.none())

        elif entry.action.value == 193:
            if entry._target_id == config.channels['vc']:
                await general.send(config.message('edit_vc_clear', member=entry.user.mention), pings=discord.AllowedMentions.none())
            elif entry._target_id == config.channels['vc2']:
                await general.send(config.message('edit_vc_2_clear', member=entry.user.mention), pings=discord.AllowedMentions.none())
            elif entry._target_id == config.channels['vc3']:
                await general.send(config.message('edit_vc_3_clear', member=entry.user.mention), pings=discord.AllowedMentions.none())


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerEventsCog(bot))
