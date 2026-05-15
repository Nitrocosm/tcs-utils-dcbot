"""SavesCog — saved-group commands: save, rename, disband."""
import logging

import discord
from discord.ext import commands

from modules import general
from modules.saves import create_save, disband_save, rename_save

log = logging.getLogger(__name__)


class SavesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command()
    @general.try_bot_perms
    async def save(self, ctx, *args):
        if not args:
            return await ctx.send("usage: `.save [name] @member1 @member2 ...`")

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

    @commands.command()
    @general.try_bot_perms
    async def rename(self, ctx, *args):
        name = " ".join(args) if args else None
        await rename_save(ctx, name)

    @commands.command()
    async def disband(self, ctx):
        await disband_save(ctx)


async def setup(bot: commands.Bot):
    await bot.add_cog(SavesCog(bot))
