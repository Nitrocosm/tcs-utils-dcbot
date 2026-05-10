import asyncio

import discord
from discord.ext import commands, tasks
from modules import config, activity, moderation, general, badges
from modules.config import TARGET_GUILD
from modules.general import timed_delete_msg, send_timed_delete_msg
from modules.role_management import RoleSession
from modules.saves import create_save, disband_save, rename_save
from modules.points import calculate_points, get_ranked_leaderboard, update_leaderboard_message, parse_challenge_role, get_member_rank, has_all_challenges, LB_EMOJI
from modules.bot_init import bot


################################################################

version = 'v5.0.6-2'

changelog = \
f"""
:tada: **{version} changelog**
- attempt automation of creating challenge roles
"""

################################################################



@tasks.loop(minutes=45)
async def member_checker():
    await activity.check_all_members()
    await activity.run_activity_checks()


@member_checker.error
async def member_checker_error(error: Exception):
    member_checker.stop()
    member_checker.start()
    await general.send(f'-# :warning: member_checker crashed :/ ```{error}```\n\n-# restarted it, but if you need to restart it manually use .force_check_all (available to mods too btw)', 'mod_chat')
    # the loop will automatically restart on next interval since we don't re-raise

@bot.event
async def on_ready():
    await general.send(f':radio_button: bot connected... {version}')
    await general.set_status('starting up...', status=discord.Status.idle) # type: ignore
    await bot.wait_until_ready()
    await general.send(f':ballot_box_with_check: restart complete!')
    await general.send(changelog)
    bot.add_view(badges.WardrobeOpenView())
    await badges.ensure_wardrobe_message(bot)
    await activity.sync_interested_reactions()
    msg = await general.send(f'-# :eye: building up activity cache', 'mod_chat')
    await activity.build_activity_cache()
    await msg.reply('-# :white_check_mark: done')
    if not member_checker.is_running():
        member_checker.start()



pings = True

@bot.command()
@general.try_bot_perms
@general.has_perms('owner')
async def p(ctx):
    global pings
    if pings:
        await ctx.message.add_reaction("🪫")
        pings = False
    else:
        await ctx.message.add_reaction("🔋")
        pings = True



@bot.command()
@general.try_bot_perms
@general.has_perms('manage_roles')
async def force_check_all(ctx):
    member_checker.stop()
    member_checker.start()
    await ctx.message.add_reaction("✅")

@bot.command()
@general.try_bot_perms
@general.has_perms('manage_roles')
async def check(ctx, member: discord.Member):
    async with RoleSession(member) as rs:
        await activity.full_check_member(rs, member)
        await send_timed_delete_msg(f'checked {member.display_name}')

@bot.command()
@general.try_bot_perms
@general.has_perms('owner')
async def test(ctx):
    await ctx.send(f'test pass\n-# {version}')

@bot.command()
@general.try_bot_perms
@general.has_perms('owner')
async def force_reactions(ctx):
    await activity.sync_interested_reactions()
    await ctx.send('uh huh')



@bot.event
async def on_command_error(ctx: commands.Context, error: Exception):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f'missing argument: `{error.param.name}`')
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send(f"couldn't find member: `{error.argument}`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f'bad argument: {error}')
    elif isinstance(error, commands.CommandNotFound):
        pass  # silently ignore unknown commands
    elif not isinstance(error, commands.CommandInvokeError):
        # CommandInvokeError means it was already handled by try_bot_perms
        await ctx.send(f'something went wrong: ```{error}```')


@bot.event
async def on_voice_state_update(member, before, after):
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

    await general.update_status(bot)


# Reaction Roles - easy hot-swap
REACTION_ROLES = {
    1451676590558937221: {  # message_id
        "⚠️": 1451675068114669740,  # emoji: role_id
    }
}


@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id: return
    activity.update_cache(payload.user_id)
    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)
    if not member or member.bot: return

    async with RoleSession(member) as rs:
        # availability logic
        if payload.message_id == config.channels['availability_message']:
            if payload.emoji.id == config.channels['availability_reaction']:
                await activity.add_availability(rs, member)

        # interested roles logic (tiered) - don't commit immediately
        interested_msgs = [
            activity.INTERESTED_MESSAGE_BASE,
            activity.INTERESTED_MESSAGE_STAR,
            activity.INTERESTED_MESSAGE_ULTIMATE
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
        if payload.message_id in REACTION_ROLES:
            emoji_str = str(payload.emoji)
            if emoji_str in REACTION_ROLES[payload.message_id]:
                rs.add(REACTION_ROLES[payload.message_id][emoji_str])


@bot.event
async def on_raw_reaction_remove(payload):
    if payload.user_id == bot.user.id: return
    activity.update_cache(payload.user_id)
    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)
    if not member or member.bot: return

    async with RoleSession(member) as rs:
        # availability logic
        if payload.message_id == config.channels['availability_message']:
            if payload.emoji.id == config.channels['availability_reaction']:
                await activity.remove_availability(rs, member)

        # interested roles logic (tiered) - don't commit immediately
        interested_msgs = [
            activity.INTERESTED_MESSAGE_BASE,
            activity.INTERESTED_MESSAGE_STAR,
            activity.INTERESTED_MESSAGE_ULTIMATE
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
        if payload.message_id in REACTION_ROLES:
            emoji_str = str(payload.emoji)
            if emoji_str in REACTION_ROLES[payload.message_id]:
                rs.remove(REACTION_ROLES[payload.message_id][emoji_str])

async def remove_availability_auto(member):
    channel = bot.get_channel(config.channels['availability'])
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
        await general.send(config.message('unavailable_auto', name=member.mention,
                                               available_count=f"{general.emojify(str(await activity.count_available(bot)), 'b')}"),
                                               pings=discord.AllowedMentions.none())


@bot.event
async def on_member_update(before, after):
    if before.roles != after.roles:
        async with RoleSession(after) as rs:
            before_roles = set(before.roles)
            after_roles = set(after.roles)
            added_roles = after_roles - before_roles
            removed_roles = before_roles - after_roles

            # track old rank before any leaderboard update
            old_rank = get_member_rank(after.guild, before)
            challenge_changed = False

            log_thread = after.guild.get_thread(1457200972215484417)

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
                await update_leaderboard_message(bot, after.guild)
                new_rank = get_member_rank(after.guild, after)

                if old_rank != new_rank and new_rank is not None:
                    emoji = LB_EMOJI.get(new_rank, "🏆")
                    await general.send(
                        f"{emoji} {after.mention}'s leaderboard position is now **#{new_rank}**!"
                    )

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
        await general.send(f':information_source:{config.message('name_change', mention=after.mention, old_name=old, new_name=new)}', 'mod_chat')




# ── Join Applications (undocumented gateway events) ──────────────────────────
# by claude :wilted:

async def _on_join_request_create(payload: dict):
    """Fires when someone submits a join application (status: PENDING)."""
    user = payload.get("user", {})
    user_id = user.get("id")
    username = user.get("global_name") or user.get("username", "unknown")
    request_id = payload.get("id")

    await general.send(
        f'<:application_add:1501552015816527963> <@{user_id}> ({username}) sent a join application',
        'mod_chat'
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
            'mod_chat'
        )
    else:
        await general.send(
            f'<:application_reject:1501552028512555039> <@{user_id}> withdrew their application\n',
            'mod_chat'
        )

import json
@bot.event
async def on_socket_raw_receive(msg: str):
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
    elif event_type == "GUILD_JOIN_REQUEST_DELETE":
        await _on_join_request_delete(payload)


@bot.event
async def on_member_join(member: discord.Member):
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



@bot.event
async def on_member_remove(member: discord.Member):
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


import re

# async def log_message(message: discord.Message):
#     if message.channel.id == config.channels['logs_channel']:
#         return
#
#     print(f'#{message.channel.name} | @{message.author.display_name} >> {message.content}')
#
#     channel = bot.get_channel(config.channels['logs_channel'])
#     timestamp = f"<t:{int(message.created_at.timestamp())}:f>"
#     content = message.content
#
#     if not content.strip() and not message.attachments and not message.stickers:
#         content = "*[no visible content]*"
#
#     log_message = (
#         f'### {message.channel.mention} >> {message.author.mention} — {timestamp}\n'
#         f'{content}\n'
#     )
#
#     attachment_urls = [attachment.url for attachment in message.attachments]
#     if attachment_urls:
#         log_message += "\n" + "\n".join(attachment_urls)
#
#     await channel.send(log_message, allowed_mentions=discord.AllowedMentions.none(), silent=True,
#                        stickers=message.stickers)

@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    if not message.guild:
        await general.send(f'***DM FROM {message.author.mention}** ({message.author.display_name})**:***\n\n{message.content}\n\n*replies to this message are automatically forwarded to the sender*', 'mod_chat')
        await message.channel.send('*your message has been forwarded to mod chat*')

    if message.guild.id == TARGET_GUILD:
        activity.update_cache(message.author.id)

        if message.content.lower() == 'ps':     # '<#1426974154556702720>' in message.content or
            await message.channel.send(
                f'link: **https://www.roblox.com/share?code=1141897d2bd9a14e955091d8a4061ee5&type=Server**',
                suppress_embeds=True)

        if message.channel == bot.get_channel(config.channels['mod_chat']) and message.reference and isinstance(message.reference.resolved, discord.Message):
            pattern = r'<@.+>'
            match = re.match(pattern, message.reference.resolved.content)
            if match:
                member_id = int(match.group(1)[2:][:-1])
                member = bot.get_user(member_id)
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

        # if isinstance(message.author, discord.Member):
        #     if '<@534097411048603648>' in message.content and \
        #             config.roles['mod'] not in [r.id for r in message.author.roles]:
        #         await message.reply(
        #             "a friendly reminder lostya is currently in rest - don't ping them without an important reason.\n"
        #             "ping moderators instead; they will escalate if necessary.\n"
        #             "-# more info: https://discord.com/channels/1426972810332340406/1434248797369663518/1490686502160695336"
        #         )
        global pings
        if not pings:
            if isinstance(message.author, discord.Member):
                if '<@534097411048603648>' in message.content:
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

        await bot.process_commands(message)


FORUM_CHANNEL_TAG_IDS = {1443764605695557753: 1456989366076313773,
                         1465308641757364397: 1467173431605985331}
ROLE_ID = 1466886852039671962
@bot.event
async def on_thread_create(thread: discord.Thread):
    await asyncio.sleep(1)
    if not isinstance(thread.parent, discord.ForumChannel):
        return
    if thread.parent_id not in FORUM_CHANNEL_TAG_IDS:
        return

    tag = thread.parent.get_tag(FORUM_CHANNEL_TAG_IDS[thread.parent_id])
    if tag:
        current_tags = thread.applied_tags
        if tag not in current_tags:
            current_tags.append(tag)
            await thread.edit(applied_tags=current_tags)

    await thread.send(f"<@&{ROLE_ID}> new challenge to verify")



from discord.ui import View, Button


class ChallengeExpandView(View):
    def __init__(self, member: discord.Member, challenges: list):
        super().__init__(timeout=60)
        self.member = member
        self.challenges = challenges
        self.expanded = False

    @discord.ui.button(label="see more challenges", style=discord.ButtonStyle.secondary)
    async def toggle_view(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.expanded = not self.expanded

        total_points, _ = calculate_points(self.member)
        ranked_lb = get_ranked_leaderboard(interaction.guild) # type: ignore

        pos_info = "*unranked*"
        for rank, points, members in ranked_lb:
            if self.member in members:
                tied = [m.mention for m in members if m.id != self.member.id]
                pos_info = f'**#{rank}** (tied with {", ".join(tied)})' if tied else f'**#{rank}**'
                break

        if self.expanded:
            display_list = '\n'.join([f'{i + 1}. <@&{role_id}>' for i, role_id in enumerate(self.challenges)])
            button.label = "see less"
        else:
            top_3 = self.challenges[:3]
            remaining = len(self.challenges) - 3
            display_list = '\n'.join([f'{i + 1}. <@&{role_id}>' for i, role_id in enumerate(top_3)])
            display_list += f'\n*(+ {remaining} more challenges...)*'
            button.label = "see more challenges"

        content = (
            f'# {self.member.mention}\'s stats\n'
            f'total life savings: `{total_points} pts`\n'
            f'total challenges completed: `{len(self.challenges)}\n`'
            f'leaderboard position: {pos_info}\n'
            f'## completed challenge list\n'
            f'{display_list}'
        )

        await interaction.response.edit_message(content=content, view=self)


async def stat_checker(ctx, member: discord.Member = None):
    if not member:
        member = ctx.author

    total_points, challenges = calculate_points(member)
    ranked_leaderboard = get_ranked_leaderboard(ctx.guild)

    position_info = "*unranked*"
    for rank, points, members in ranked_leaderboard:
        if member in members:
            tied_members_mentions = [m.mention for m in members if m.id != member.id]
            position_info = f'**#{rank}** (tied with {", ".join(tied_members_mentions)})' if tied_members_mentions else f'**#{rank}**'
            break

    view = None
    challenge_count = len(challenges)

    if challenge_count > 3:
        top_3 = challenges[:3]
        remaining = challenge_count - 3
        challenge_list = '\n'.join([f'{i + 1}. <@&{role_id}>' for i, role_id in enumerate(top_3)])
        challenge_list += f'\n*(+ {remaining} more challenges...)*'
        view = ChallengeExpandView(member, challenges)
    else:
        challenge_list = '\n'.join([f'{i + 1}. <@&{role_id}>' for i, role_id in enumerate(challenges)])
        if not challenge_list:
            challenge_list = '*none*'

    response = (
        f'# {member.mention}\'s stats\n'
        f'total life savings: `{total_points} pts`\n'
        f'total challenges completed: `{challenge_count}\n`'
        f'leaderboard position: {position_info}\n'
        f'## completed challenge list\n'
        f'{challenge_list}'
    )

    await ctx.send(response, view=view, allowed_mentions=discord.AllowedMentions.none())



@bot.command()
@general.try_bot_perms
async def points(ctx, member: discord.Member = None):
    await stat_checker(ctx, member)


@bot.command()
@general.try_bot_perms
async def pts(ctx, member: discord.Member = None):
    await stat_checker(ctx, member)


@bot.command()
@general.try_bot_perms
async def stats(ctx, member: discord.Member = None):
    await stat_checker(ctx, member)


@bot.command()
@general.try_bot_perms
async def save(ctx, *args):
    if not args:
        return await ctx.send("usage: `.save [name] @member1 @member2 ...`")

    # Parse arguments - check if first arg is a member or a name
    # save_name = None
    # members = []
    #
    # for i, arg in enumerate(args):
    #     try:
    #         member = await commands.MemberConverter().convert(ctx, arg)
    #         members.append(member)
    #     except commands.MemberNotFound:
    #         # If it's the first argument, and we have no members yet, treat as name
    #         if i == 0 and not members:
    #             save_name = arg
    #         else:
    #             return await ctx.send(f"couldn't find member: `{arg}`")

    name_parts = []
    members = []
    name_done = False

    for arg in args:
        try:
            member = await commands.MemberConverter().convert(ctx, arg)
            members.append(member)
            name_done = True
        except commands.MemberNotFound:
            if name_done or members:
                return await ctx.send(f"couldn't find member: `{arg}`")
            name_parts.append(arg)

    save_name = " ".join(name_parts) if name_parts else None

    if not members:
        return await ctx.send("usage: `.save [name] @member1 @member2 ...`")

    return await create_save(ctx, members, save_name)


@bot.command()
@general.try_bot_perms
async def rename(ctx, *args):
    name = " ".join(args) if args else None
    await rename_save(ctx, name)


@bot.command()
async def disband(ctx):
    await disband_save(ctx)


@bot.command()
@general.try_bot_perms
async def van(ctx, member: discord.Member = None, *, reason: str = None):
    msg = f'{member.mention} has been vanned :white_check_mark:'
    if reason:
        msg += f'\nreason: {reason}'
    await ctx.send(msg)


@bot.command()
@general.try_bot_perms
async def war(ctx, member: discord.Member = None, *, reason: str = None):
    msg = f'{member.mention} has been warred :white_check_mark:'
    if reason:
        msg += f'\nreason: {reason}'
    await ctx.send(msg)


@bot.command()
@general.try_bot_perms
@general.has_perms('manage_messages')
async def pin(ctx):
    if not ctx.message.reference or not ctx.message.reference.resolved:
        return await ctx.send("you have to reply to a message to pin it")
    msg = ctx.message.reference.resolved
    return await msg.pin()

@bot.command()
@general.try_bot_perms
@general.has_perms('manage_messages')
async def unpin(ctx):
    if not ctx.message.reference or not ctx.message.reference.resolved:
        return await ctx.send("you have to reply to a message to unpin it")
    msg = ctx.message.reference.resolved
    return await msg.unpin()


@bot.command()
@general.try_bot_perms
@general.has_perms('kick_members')
@general.can_moderate_member
async def kick(ctx, member: discord.Member = None, *, reason: str = None):
    await member.kick(reason=reason)


@bot.command()
@general.try_bot_perms
@general.has_perms('ban_members')
@general.can_moderate_member
async def ban(ctx, member: discord.Member = None, *, reason: str = None):
    await member.ban(reason=reason, delete_message_seconds=0)


@bot.command()
@general.try_bot_perms
@general.has_perms('moderate_members')
@general.can_moderate_member
async def mute(ctx, member: discord.Member = None, duration: str = None, *, reason: str = None):
    if not duration:
        await ctx.send('u forgot to specify duration bro. i gotchu tho. default value is 5 min')
        duration = '5m'

    timeout_duration = moderation.get_timeout_duration(duration)
    await member.timeout(timeout_duration, reason=reason)

    formatted_duration = moderation.format_timedelta(timeout_duration)
    await ctx.send(f"muted the guy for {formatted_duration} :white_check_mark:")


@bot.command()
@general.try_bot_perms
@general.has_perms('moderate_members')
@general.can_moderate_member
async def unmute(ctx, member: discord.Member = None, *, reason: str = None):
    await moderation.unmute(ctx, member, reason)


@bot.command()
@general.try_bot_perms
@general.has_perms('moderate_members')
@general.can_moderate_member
async def warn(ctx, member: discord.Member = None, *, reason: str = None):
    await moderation.warn(ctx, member, reason)


@bot.command()
@general.try_bot_perms
async def warns(ctx, member: discord.Member = None):
    if member.guild.get_role(config.roles['warn_1']) in member.roles:
        await ctx.send(f"this guy has 1 warn :yellow_circle:")
    elif member.guild.get_role(config.roles['warn_2']) in member.roles:
        await ctx.send(f"this guy has 2 warns :orange_circle:")
    elif member.guild.get_role(config.roles['warn_3']) in member.roles:
        await ctx.send(f"this guy has 3 warns :red_circle:\n-# next warn will ban them btw")
    else:
        await ctx.send(f"this guy doesn't have warns they're an outstanding citizen :white_check_mark:")

@bot.command()
@general.try_bot_perms
@general.has_perms('moderate_members')
@general.can_moderate_member
async def clear_warns(ctx, member: discord.Member = None):
    await member.timeout(None)
    async with RoleSession(member) as rs:
        rs.remove(general.config.roles['warn_1'])
        rs.remove(general.config.roles['warn_2'])
        rs.remove(general.config.roles['warn_3'])
    await ctx.send(f"cleared all warns :white_check_mark:")

@bot.command()
@general.try_bot_perms
@general.has_perms('manage_channels')
async def lock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send(config.message("channel_lock"))

@bot.command()
@general.try_bot_perms
@general.has_perms('manage_channels')
async def unlock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=None)
    await ctx.send(config.message("channel_unlock"))


from discord.ui import View, button
class ConfirmDeleteView(View):
    def __init__(self, author: discord.User):
        super().__init__(timeout=30)
        self.author = author
        self.result = None

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.defer(ephemeral=True) # type: ignore
            await interaction.followup.send("this confirmation ain't for you pal", ephemeral=True)
            return False
        return True

    @button(label="proceed", style=discord.ButtonStyle.danger) # type: ignore
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = True
        await interaction.message.edit(content=":wastebasket: proceeding with deletion...", view=None)
        self.stop()

    @button(label="cancel", style=discord.ButtonStyle.secondary) # type: ignore
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = False
        await interaction.message.edit(content="❌ deletion canceled", view=None)
        self.stop()


@bot.command()
@general.has_perms('manage_messages')
@general.try_bot_perms
async def r(ctx, start_id: int, end_id: int = None):
    channel = ctx.channel
    await ctx.message.delete()

    res_msg = await ctx.send(f':brain: finding messages to delete')

    if end_id is None:
        if start_id > 30:
            return await general.timed_delete_msg(res_msg, 'u tried to delete >30 msgs with recent deletion, make sure u doin the right thing. to delete more than 30 use message ids')

        messages = []
        async for msg in channel.history(limit=start_id+1):  # +1 to skip the res_msg
            if msg.id != res_msg.id:
                messages.append(msg)

        await channel.delete_messages(messages)
        return await timed_delete_msg(res_msg, f'deleted {len(messages)} recent messages', 5)

    else:
        try:
            start_message = await channel.fetch_message(start_id)
            end_message = await channel.fetch_message(end_id)
        except discord.NotFound:
            return await timed_delete_msg(res_msg, 'one of the message ids wasn\'t found, make sure u doin the right thing', 10)
        except discord.HTTPException as e:
            return await timed_delete_msg(res_msg, f'unable to fetch msgs: {e}', 10)

        if start_message.created_at > end_message.created_at:
            start_message, end_message = end_message, start_message

        await res_msg.edit(content=':brain: selecting messages to delete')
        messages_to_delete = []
        async for message in channel.history(
            limit=None,
            before=end_message.created_at,
            after=start_message.created_at,
        ):
            messages_to_delete.append(message)

        if start_message not in messages_to_delete:
            messages_to_delete.append(start_message)
        if end_message not in messages_to_delete:
            messages_to_delete.append(end_message)

        await res_msg.edit(content=':brain: sorting messages to delete')
        messages_to_delete.sort(key=lambda m: m.created_at)

        if not messages_to_delete:
            return await timed_delete_msg(res_msg, f'there are no messages between those ids', 10)


        total_to_delete = len(messages_to_delete)
        if total_to_delete > 50:
            view = ConfirmDeleteView(ctx.author)
            await res_msg.edit(content=f'⚠️ ur about to delete **{total_to_delete} messages**. u sure?', view=view)
            await view.wait()

            if view.result is None or not view.result:
                return await timed_delete_msg(res_msg, 'deletion cancelled', 10)


        total_deleted = 0
        message_chunks = [messages_to_delete[i:i + 100] for i in range(0, len(messages_to_delete), 100)]

        for chunk in message_chunks:
            await res_msg.edit(content=f':wastebasket: deleting {len(chunk)} messages (total so far: {total_deleted}) (total to delete: {len(messages_to_delete)})')
            await channel.delete_messages(chunk)
            total_deleted += len(chunk)
            await asyncio.sleep(1)

        return await timed_delete_msg(res_msg, f'deleted {total_deleted} messages', 10)


@bot.command()
@general.try_bot_perms
@general.has_perms('owner')
async def update(ctx):
    import subprocess
    await ctx.send(':radio_button: pulling from git...')
    try:
        result = subprocess.run(
            ['git', 'pull'],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            return await ctx.send(f':warning: git pull failed\n```{result.stderr}```')
        await ctx.send(f'```{result.stdout}```')
        await ctx.send(f':radio_button: restarting bot...')
        subprocess.Popen(['systemctl', 'restart', '--user', 'tcs-utils-dcbot'])

    except subprocess.TimeoutExpired:
        await ctx.send(':x: git pull timed out')
    except Exception as e:
        await ctx.send(f':x: error: ```{e}```')


@bot.command()
@general.try_bot_perms
@general.has_perms('manage_roles')
async def check_inactive_people(ctx):
    await activity.check_inactivity()


@bot.command()
@general.try_bot_perms
@general.has_perms('manage_roles')
async def unavailable(ctx, member: discord.Member):
    # await remove_availability_auto(member)
    async with RoleSession(member) as rs:
        rs.remove(config.roles['available'])



CHALLENGE_ROLE_CATEGORIES = {
    "badge":     "badges",       # fragment of your badges category name
    "display":   "display",      # fragment of your display badge category name
    "pingable":  "pingable",     # fragment of your pingable/interested category name
}


def _find_category_role(
    guild: discord.Guild, name_fragment: str
) -> discord.Role | None:
    """Find a category role whose name contains name_fragment (case-insensitive)."""
    for role in guild.roles:
        if role.name.startswith("──╱") and name_fragment.lower() in role.name.lower():
            return role
    return None


def _get_category_bottom_position(
    guild: discord.Guild, category_role: discord.Role
) -> int:
    """
    Return the position a new role should be placed at — just above the
    'none' role in the category, or just above the next category/floor.
    Roles are ordered lowest position = bottom in Discord's hierarchy.
    """
    sorted_roles = sorted(guild.roles, key=lambda r: r.position, reverse=True)

    in_category = False
    last_position = category_role.position

    for role in sorted_roles:
        if role.id == category_role.id:
            in_category = True
            continue

        if not in_category:
            continue

        # hit another category or @everyone → stop
        if role.name.startswith("──╱") or role.is_default():
            break

        last_position = role.position

    # place at the very bottom of this category (lowest position within it)
    return max(last_position - 1, 1)






import re
from dataclasses import dataclass

import discord
from discord.ext import commands


CATEGORY_BADGES = "──╱ badges ╱"
CATEGORY_DISPLAY = "──╱ display badge ╱"
CATEGORY_PINGABLE = "──╱ pingable challenge list ╱"

HEADER_PREFIX = "──╱"
EMPTY_DIVIDER_NAME = ""

POINTS_RE = re.compile(r"/\+?(\d+)(?:/|$)")


@dataclass(frozen=True)
class ChallengeVisuals:
    badge_prefix: str
    pingable_suffix: str
    icon_emoji_name: str
    primary: int | None = None
    secondary: int | None = None
    tertiary: int | None = None


def _visuals_for_points(points: int) -> ChallengeVisuals:
    # always assume base challenge -> green circle
    if points == 0:
        return ChallengeVisuals(
            badge_prefix="💠🟢",
            pingable_suffix="💠",
            icon_emoji_name="badge_placeholder_custom_npc",
            primary=0x3498DB,
        )
    if 1 <= points <= 2:
        return ChallengeVisuals(
            badge_prefix="💠🟢",
            pingable_suffix="💠",
            icon_emoji_name="badge_placeholder_custom_normal",
            primary=0x42AC6E,
        )
    if 3 <= points <= 4:
        return ChallengeVisuals(
            badge_prefix="💠🟢",
            pingable_suffix="💠",
            icon_emoji_name="badge_placeholder_custom_hard",
            primary=0x37B86D,
            secondary=0x8CD450,
        )
    if 5 <= points <= 7:
        return ChallengeVisuals(
            badge_prefix="💠🟢",
            pingable_suffix="💠",
            icon_emoji_name="badge_placeholder_custom_insane",
            primary=0xBE7A3A,
            secondary=0xF5C34F,
        )
    if 8 <= points <= 10:
        return ChallengeVisuals(
            badge_prefix="💠🟢",
            pingable_suffix="💠",
            icon_emoji_name="badge_placeholder_custom_extreme",
            primary=0xAA3B3B,
            secondary=0xFF4848,
        )
    if 11 <= points <= 13:
        return ChallengeVisuals(
            badge_prefix="💠🟢",
            pingable_suffix="💠",
            icon_emoji_name="badge_placeholder_custom_brutal",
            primary=0x7D5FCF,
            secondary=0xCB62F5,
        )
    if 14 <= points <= 17:
        return ChallengeVisuals(
            badge_prefix="💠🟢",
            pingable_suffix="💠",
            icon_emoji_name="badge_placeholder_custom_maso",
            primary=0x51F37C,
            secondary=0x8943F5,
        )
    if 18 <= points <= 23:
        return ChallengeVisuals(
            badge_prefix="💠🟢",
            pingable_suffix="💠",
            icon_emoji_name="badge_placeholder_custom_leg",
            primary=0x69ADFF,
            secondary=0xEC97FF,
        )

    # 24+: holographic preset
    return ChallengeVisuals(
        badge_prefix="💠🟢",
        pingable_suffix="💠",
        icon_emoji_name="badge_placeholder_custom_godlike",
        primary=11127295,
        secondary=16759788,
        tertiary=16761760,
    )


def _roles_top_to_bottom(guild: discord.Guild) -> list[discord.Role]:
    return sorted(guild.roles, key=lambda r: r.position, reverse=True)


def _is_header_role(role: discord.Role) -> bool:
    return role.name.startswith(HEADER_PREFIX)


def _find_header_role(guild: discord.Guild, fragment: str) -> discord.Role | None:
    for role in _roles_top_to_bottom(guild):
        if fragment in role.name:
            return role
    return None


def _block_bounds(guild: discord.Guild, header: discord.Role) -> tuple[int, int]:
    """
    Returns:
        (upper_exclusive, lower_exclusive)

    Roles visually inside the section satisfy:
        lower_exclusive < role.position < upper_exclusive
    """
    headers = [r for r in _roles_top_to_bottom(guild) if _is_header_role(r)]
    index = headers.index(header)

    next_header = headers[index + 1] if index + 1 < len(headers) else None
    upper_exclusive = header.position
    lower_exclusive = next_header.position if next_header else 0
    return upper_exclusive, lower_exclusive


def _roles_in_block(guild: discord.Guild, header: discord.Role) -> list[discord.Role]:
    upper_exclusive, lower_exclusive = _block_bounds(guild, header)
    return [
        role
        for role in _roles_top_to_bottom(guild)
        if lower_exclusive < role.position < upper_exclusive
    ]


def _custom_divider_and_roles(
    guild: discord.Guild, header: discord.Role
) -> tuple[discord.Role | None, list[discord.Role]]:
    """
    Returns:
        (divider_role, custom_roles_top_to_bottom)

    Assumes the section layout is:
        official roles
        empty divider role
        custom roles
    """
    roles = _roles_in_block(guild, header)

    divider_index = None
    for i, role in enumerate(roles):
        if role.name == EMPTY_DIVIDER_NAME:
            divider_index = i
            break

    if divider_index is None:
        return None, []

    divider = roles[divider_index]
    custom_roles = roles[divider_index + 1 :]
    return divider, custom_roles


def _extract_points(role_name: str) -> int:
    match = POINTS_RE.search(role_name)
    if not match:
        return -1
    return int(match.group(1))


def _custom_sort_key(role: discord.Role) -> tuple[int, str]:
    return (-_extract_points(role.name), role.name.casefold())


async def _emoji_bytes_by_name(guild: discord.Guild, emoji_name: str) -> bytes | None:
    emoji = discord.utils.get(guild.emojis, name=emoji_name)
    if emoji is None:
        return None

    try:
        return await emoji.read()
    except discord.HTTPException:
        return None


async def _apply_visuals_to_role(
    role: discord.Role,
    visuals: ChallengeVisuals,
    *,
    reason: str,
) -> None:
    kwargs = {
        "colour": discord.Colour(visuals.primary) if visuals.primary is not None else None,
        "secondary_colour": (
            discord.Colour(visuals.secondary)
            if visuals.secondary is not None
            else None
        ),
        "tertiary_colour": (
            discord.Colour(visuals.tertiary)
            if visuals.tertiary is not None
            else None
        ),
        "reason": reason,
    }

    # remove None values except reason
    kwargs = {k: v for k, v in kwargs.items() if v is not None or k == "reason"}
    await role.edit(**kwargs)


async def _place_custom_roles(
    guild: discord.Guild,
    header: discord.Role,
    final_custom_roles_top_to_bottom: list[discord.Role],
    *,
    reason: str,
) -> None:
    """
    Rebuilds only the custom subsection under the given header.

    The custom subsection is the part below the empty divider and above
    the next header.
    """
    divider, _existing_custom = _custom_divider_and_roles(guild, header)
    if divider is None:
        raise RuntimeError(
            f"Could not find empty divider in section `{header.name}`"
        )

    _upper_exclusive, lower_exclusive = _block_bounds(guild, header)

    target_positions = list(
        range(divider.position - 1, lower_exclusive, -1)
    )

    if len(final_custom_roles_top_to_bottom) > len(target_positions):
        raise RuntimeError(
            f"Not enough slots in custom subsection under `{header.name}`"
        )

    position_map = {
        role: position
        for role, position in zip(
            final_custom_roles_top_to_bottom,
            target_positions,
            strict=False,
        )
    }

    await guild.edit_role_positions(position_map, reason=reason)



@bot.command()
@general.has_perms("owner")
@general.try_bot_perms
async def create_challenge(
    ctx: commands.Context,
    points: int,
    *,
    name: str,
):
    """
    Usage:
        .create_challenge <points> <challenge name>

    Example:
        .create_challenge 6 Tick Tock
    """
    guild = ctx.guild
    if guild is None:
        await ctx.send("❌ this command can only be used in a server")
        return

    if points < 0:
        await ctx.send("❌ points must be 0 or higher")
        return

    status = await ctx.send(
        f"⏳ creating challenge roles for **{name}** "
        f"(**{points}** points)..."
    )

    headers = {
        "badges": _find_header_role(guild, CATEGORY_BADGES),
        "display": _find_header_role(guild, CATEGORY_DISPLAY),
        "pingable": _find_header_role(guild, CATEGORY_PINGABLE),
    }

    missing = [key for key, role in headers.items() if role is None]
    if missing:
        await status.edit(
            content=(
                "❌ missing required header role(s): "
                + ", ".join(f"`{m}`" for m in missing)
            ),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    visuals = _visuals_for_points(points)
    reason = (
        f"challenge creation by {ctx.author} "
        f"for {name} ({points} points)"
    )

    badge_name = f"🆕{visuals.badge_prefix} {name} /+{points}/"
    display_name = f"🆕👁 {name}"
    pingable_name = f"🆕 {name} /{points}/{visuals.pingable_suffix}"

    errors: list[str] = []
    notes: list[str] = []
    created_roles: dict[str, discord.Role] = {}

    # Step 1: create the roles.
    try:
        created_roles["badges"] = await guild.create_role(
            name=badge_name,
            mentionable=False,
            reason=reason,
        )
        created_roles["display"] = await guild.create_role(
            name=display_name,
            mentionable=False,
            reason=reason,
        )
        created_roles["pingable"] = await guild.create_role(
            name=pingable_name,
            mentionable=True,
            reason=reason,
        )
    except discord.Forbidden:
        await status.edit(
            content=(
                "❌ missing permissions to create roles. "
                "Check `Manage Roles` and bot role hierarchy."
            ),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return
    except discord.HTTPException as e:
        await status.edit(
            content=f"❌ failed to create roles: `{e}`",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    # Step 2: style the badge + pingable roles with the proper colours.
    try:
        await _apply_visuals_to_role(
            created_roles["badges"],
            visuals,
            reason=reason,
        )
    except discord.Forbidden:
        errors.append("❌ could not apply colours to the badge role")
    except discord.HTTPException as e:
        errors.append(f"❌ failed to apply colours to the badge role: `{e}`")

    try:
        await _apply_visuals_to_role(
            created_roles["pingable"],
            visuals,
            reason=reason,
        )
    except discord.Forbidden:
        errors.append("❌ could not apply colours to the pingable role")
    except discord.HTTPException as e:
        errors.append(f"❌ failed to apply colours to the pingable role: `{e}`")

    # Step 3: set the display badge icon from the server emoji.
    try:
        icon_bytes = await _emoji_bytes_by_name(guild, visuals.icon_emoji_name)
        if icon_bytes is None:
            notes.append(
                f"⚠️ could not find or read emoji "
                f"`:{visuals.icon_emoji_name}:`, so no display role icon was set"
            )
        else:
            await created_roles["display"].edit(
                display_icon=icon_bytes,
                reason=reason,
            )
    except discord.Forbidden:
        errors.append("❌ could not set the display badge icon")
    except discord.HTTPException as e:
        errors.append(f"❌ failed to set the display badge icon: `{e}`")

    # Step 4: place the badge role among custom badge roles, sorted by points.
    try:
        badges_header = headers["badges"]
        assert badges_header is not None

        _divider, existing_custom_badges = _custom_divider_and_roles(
            guild, badges_header
        )
        final_custom_badges = existing_custom_badges + [created_roles["badges"]]
        final_custom_badges.sort(key=_custom_sort_key)

        await _place_custom_roles(
            guild,
            badges_header,
            final_custom_badges,
            reason=reason,
        )
    except discord.Forbidden:
        errors.append("❌ could not move the badge role into its section")
    except Exception as e:
        errors.append(f"❌ failed to place the badge role: `{e}`")

    # Step 5: place the display badge role at the end of the custom display subsection.
    try:
        display_header = headers["display"]
        assert display_header is not None

        _divider, existing_custom_display = _custom_divider_and_roles(
            guild, display_header
        )
        final_custom_display = existing_custom_display + [created_roles["display"]]

        await _place_custom_roles(
            guild,
            display_header,
            final_custom_display,
            reason=reason,
        )
    except discord.Forbidden:
        errors.append("❌ could not move the display badge role into its section")
    except Exception as e:
        errors.append(f"❌ failed to place the display badge role: `{e}`")

    # Step 6: place the pingable role among custom pingable roles, sorted by points.
    try:
        pingable_header = headers["pingable"]
        assert pingable_header is not None

        _divider, existing_custom_pingables = _custom_divider_and_roles(
            guild, pingable_header
        )
        final_custom_pingables = (
            existing_custom_pingables + [created_roles["pingable"]]
        )
        final_custom_pingables.sort(key=_custom_sort_key)

        await _place_custom_roles(
            guild,
            pingable_header,
            final_custom_pingables,
            reason=reason,
        )
    except discord.Forbidden:
        errors.append("❌ could not move the pingable role into its section")
    except Exception as e:
        errors.append(f"❌ failed to place the pingable role: `{e}`")

    lines = [
        f"✅ challenge roles created for **{name}** (**{points}** points)",
        f"• badge: {created_roles['badges'].mention}",
        f"• display: {created_roles['display'].mention}",
        f"• pingable: {created_roles['pingable'].mention}",
    ]

    if notes:
        lines.append("")
        lines.extend(notes)

    if errors:
        lines.append("")
        lines.extend(errors)

    await status.edit(
        content="\n".join(lines),
        allowed_mentions=discord.AllowedMentions.none(),
    )



if __name__ == '__main__':
    bot.run(config.TOKEN)