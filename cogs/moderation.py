"""ModerationCog — kick/ban/mute/warn/etc., channel locks, message purge, jokes."""
import asyncio
import logging

import discord
from discord.ext import commands
from discord.ui import View, button

from modules import config, general, moderation
from modules.general import timed_delete_msg
from modules.role_management import RoleSession

log = logging.getLogger(__name__)


class ConfirmDeleteView(View):
    def __init__(self, author: discord.User):
        super().__init__(timeout=30)
        self.author = author
        self.result = None

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.defer(ephemeral=True)  # type: ignore
            await interaction.followup.send("this confirmation ain't for you pal", ephemeral=True)
            return False
        return True

    @button(label="proceed", style=discord.ButtonStyle.danger)  # type: ignore
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = True
        await interaction.message.edit(content=":wastebasket: proceeding with deletion...", view=None)
        self.stop()

    @button(label="cancel", style=discord.ButtonStyle.secondary)  # type: ignore
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = False
        await interaction.message.edit(content="❌ deletion canceled", view=None)
        self.stop()


class ModerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── jokes ───────────────────────────────────────────────────────────────

    @commands.command()
    @general.try_bot_perms
    async def van(self, ctx, member: discord.Member = None, *, reason: str = None):
        msg = f'{member.mention} has been vanned :white_check_mark:'
        if reason:
            msg += f'\nreason: {reason}'
        await ctx.send(msg)

    @commands.command()
    @general.try_bot_perms
    async def war(self, ctx, member: discord.Member = None, *, reason: str = None):
        msg = f'{member.mention} has been warred :white_check_mark:'
        if reason:
            msg += f'\nreason: {reason}'
        await ctx.send(msg)

    # ── pin / unpin ─────────────────────────────────────────────────────────

    @commands.command()
    @general.try_bot_perms
    @general.has_perms('manage_messages')
    async def pin(self, ctx):
        if not ctx.message.reference or not ctx.message.reference.resolved:
            return await ctx.send("you have to reply to a message to pin it")
        msg = ctx.message.reference.resolved
        return await msg.pin()

    @commands.command()
    @general.try_bot_perms
    @general.has_perms('manage_messages')
    async def unpin(self, ctx):
        if not ctx.message.reference or not ctx.message.reference.resolved:
            return await ctx.send("you have to reply to a message to unpin it")
        msg = ctx.message.reference.resolved
        return await msg.unpin()

    # ── kick / ban / mute / unmute ──────────────────────────────────────────

    @commands.command()
    @general.try_bot_perms
    @general.has_perms('kick_members')
    @general.can_moderate_member
    async def kick(self, ctx, member: discord.Member = None, *, reason: str = None):
        try:
            await member.send(
                f'hey there! you got kicked from **these challenges suck** for the following reason:\n'
                f'> {reason}\n'
                f'\n'
                f"this isn't a ban. [you can freely reapply to the server at any point if you wish!](https://discord.gg/AU2yAuXJQ7)"
            )
            await ctx.send('-# sent the kicked guy a dm btw')
        except discord.HTTPException:
            log.warning("kick: failed to DM kicked member", exc_info=True)
            await ctx.send('-# couldnt send the guy a dm bc discord dumb asf')
        await member.kick(reason=reason)

    @commands.command()
    @general.try_bot_perms
    @general.has_perms('ban_members')
    @general.can_moderate_member
    async def ban(self, ctx, member: discord.Member = None, *, reason: str = None):
        await member.ban(reason=reason, delete_message_seconds=0)

    @commands.command()
    @general.try_bot_perms
    @general.has_perms('moderate_members')
    @general.can_moderate_member
    async def mute(self, ctx, member: discord.Member = None, duration: str = None, *, reason: str = None):
        if not duration:
            await ctx.send('u forgot to specify duration bro. i gotchu tho. default value is 5 min')
            duration = '5m'

        timeout_duration = moderation.get_timeout_duration(duration)
        await member.timeout(timeout_duration, reason=reason)

        formatted_duration = moderation.format_timedelta(timeout_duration)
        await ctx.send(f"muted the guy for {formatted_duration} :white_check_mark:")

    @commands.command()
    @general.try_bot_perms
    @general.has_perms('moderate_members')
    @general.can_moderate_member
    async def unmute(self, ctx, member: discord.Member = None, *, reason: str = None):
        await moderation.unmute(ctx, member, reason)

    # ── warnings ────────────────────────────────────────────────────────────

    @commands.command()
    @general.try_bot_perms
    @general.has_perms('moderate_members')
    @general.can_moderate_member
    async def warn(self, ctx, member: discord.Member = None, *, reason: str = None):
        await moderation.warn(ctx, member, reason)

    @commands.command()
    @general.try_bot_perms
    async def warns(self, ctx, member: discord.Member = None):
        if member.guild.get_role(config.roles['warn_1']) in member.roles:
            await ctx.send("this guy has 1 warn :yellow_circle:")
        elif member.guild.get_role(config.roles['warn_2']) in member.roles:
            await ctx.send("this guy has 2 warns :orange_circle:")
        elif member.guild.get_role(config.roles['warn_3']) in member.roles:
            await ctx.send("this guy has 3 warns :red_circle:\n-# next warn will ban them btw")
        else:
            await ctx.send("this guy doesn't have warns they're an outstanding citizen :white_check_mark:")

    @commands.command()
    @general.try_bot_perms
    @general.has_perms('moderate_members')
    @general.can_moderate_member
    async def clear_warns(self, ctx, member: discord.Member = None):
        async with RoleSession(member) as rs:
            rs.remove(config.roles['warn_1'])
            rs.remove(config.roles['warn_2'])
            rs.remove(config.roles['warn_3'])
        await ctx.send("cleared all warns :white_check_mark:")

    # ── channel lock / unlock ───────────────────────────────────────────────

    @commands.command()
    @general.try_bot_perms
    @general.has_perms('manage_channels')
    async def lock(self, ctx):
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
        await ctx.send(config.message("channel_lock"))

    @commands.command()
    @general.try_bot_perms
    @general.has_perms('manage_channels')
    async def unlock(self, ctx):
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=None)
        await ctx.send(config.message("channel_unlock"))

    # ── message purge ───────────────────────────────────────────────────────

    @commands.command()
    @general.has_perms('manage_messages')
    @general.try_bot_perms
    async def r(self, ctx, start_id: int, end_id: int = None):
        channel = ctx.channel
        await ctx.message.delete()

        res_msg = await ctx.send(':brain: finding messages to delete')

        if end_id is None:
            if start_id > 30:
                return await general.timed_delete_msg(res_msg, 'u tried to delete >30 msgs with recent deletion, make sure u doin the right thing. to delete more than 30 use message ids')

            messages = []
            async for msg in channel.history(limit=start_id + 1):  # +1 to skip the res_msg
                if msg.id != res_msg.id:
                    messages.append(msg)

            await channel.delete_messages(messages)
            return await timed_delete_msg(res_msg, f'deleted {len(messages)} recent messages', 5)

        else:
            try:
                start_message = await channel.fetch_message(start_id)
                end_message = await channel.fetch_message(end_id)
            except discord.NotFound:
                return await timed_delete_msg(res_msg, "one of the message ids wasn't found, make sure u doin the right thing", 10)
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
                return await timed_delete_msg(res_msg, 'there are no messages between those ids', 10)

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


async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))
