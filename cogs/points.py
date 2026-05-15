"""PointsCog — stats / leaderboard display commands."""
import logging

import discord
from discord.ext import commands
from discord.ui import View

from modules import general
from modules.points import calculate_points, get_ranked_leaderboard

log = logging.getLogger(__name__)


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
        ranked_lb = get_ranked_leaderboard(interaction.guild)  # type: ignore

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


class PointsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(aliases=['pts', 'stats'])
    @general.try_bot_perms
    async def points(self, ctx, member: discord.Member = None):
        await stat_checker(ctx, member)


async def setup(bot: commands.Bot):
    await bot.add_cog(PointsCog(bot))
