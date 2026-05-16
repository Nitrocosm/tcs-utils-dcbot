import re
import discord
from typing import Optional, List, Tuple
from modules import config
from modules.role_management import RoleSession

LB_EMOJI = {
    1: config.emoji["lb_top_1"],
    2: config.emoji["lb_top_2"],
    3: config.emoji["lb_top_3"],
}

TOP_ROLES = {
    1: config.roles["lb_top_1"],
    2: config.roles["lb_top_2"],
    3: config.roles["lb_top_3"],
}

DISPLAY_ROLES = {
    1: config.roles["lb_display_top_1"],
    2: config.roles["lb_display_top_2"],
    3: config.roles["lb_display_top_3"],
}

DISPLAY_NOT_TOP = config.roles["lb_display_not_top"]


def parse_challenge_role(role: discord.Role) -> Optional[dict]:
    """Parse a challenge role and extract information."""
    if not role.name.startswith('🏆') and not role.name.startswith('💠'):
        return None

    pattern = r'^[🏆💠]([🟢⭐☄])\s+(.+?)\s+/\+(\d+)/$'
    match = re.match(pattern, role.name)

    if not match:
        return None

    tier_emoji, name, points = match.groups()
    return {
        'tier_emoji': tier_emoji,
        'name': name,
        'points': int(points),
        'role': role.id
    }


def calculate_points(member: discord.Member) -> tuple[int, List[int]]:
    total = 0
    challenge_roles = []
    for role in member.roles:
        role_info = parse_challenge_role(role)
        if role_info:
            total += role_info['points']
            challenge_roles.append((role_info['points'], role.id))
    challenge_roles.sort(reverse=True, key=lambda x: x[0])
    return total, [role_id for _, role_id in challenge_roles]


def get_leaderboard(guild: discord.Guild) -> List[Tuple[discord.Member, int]]:
    """Get leaderboard sorted by points."""
    leaderboard = []

    for member in guild.members:
        if member.bot:
            continue
        total_points, _ = calculate_points(member)
        if total_points > 0:
            leaderboard.append((member, total_points))

    leaderboard.sort(key=lambda x: (-x[1], x[0].id))
    return leaderboard


def get_ranked_leaderboard(guild: discord.Guild) -> list[tuple[int, int, list[discord.Member]]]:
    leaderboard = get_leaderboard(guild)

    ranked_entries: list[tuple[int, int, list[discord.Member]]] = []
    previous_points = None
    unique_rank = 0

    for member, points in leaderboard:
        if points != previous_points:
            unique_rank += 1
            ranked_entries.append((unique_rank, points, [member]))
        else:
            ranked_entries[-1][2].append(member)
        previous_points = points

    return ranked_entries


def get_member_rank(guild: discord.Guild, member: discord.Member) -> Optional[int]:
    """Get the leaderboard rank of a member (1-indexed). Returns None if not ranked."""
    ranked_lb = get_ranked_leaderboard(guild)
    for rank, _, members in ranked_lb:
        if member in members:
            return rank
    return None


def has_all_challenges(member: discord.Member, tiers: set[str]) -> bool:
    """Check if member has all challenge roles for given tiers."""
    all_required_roles = [
        r for r in member.guild.roles
        if parse_challenge_role(r)
           and parse_challenge_role(r)["tier_emoji"] in tiers
           and parse_challenge_role(r)["points"] > 0
           and not r.name.startswith("💠")
    ]

    owned = {
        r.id for r in member.roles
        if parse_challenge_role(r)
           and parse_challenge_role(r)["tier_emoji"] in tiers
           and parse_challenge_role(r)["points"] > 0
           and not r.name.startswith("💠")
    }

    return len(all_required_roles) > 0 and all(r.id in owned for r in all_required_roles)


async def sync_leaderboard_roles(guild: discord.Guild, ranked_leaderboard: list):
    """Sync leaderboard roles for all members based on their rank."""
    top_map = {}

    for rank, _, members in ranked_leaderboard:
        if rank > 3:
            break
        for m in members:
            top_map[m.id] = rank

    for member in guild.members:
        if member.bot:
            continue

        async with RoleSession(member) as rs:
            rs.remove(
                config.roles["lb_top_1"],
                config.roles["lb_top_2"],
                config.roles["lb_top_3"],
            )

            rank = top_map.get(member.id)
            if rank:
                rs.add(TOP_ROLES[rank])

            has_display_opt_in = any(
                r.id in (
                    config.roles["lb_display_top_1"],
                    config.roles["lb_display_top_2"],
                    config.roles["lb_display_top_3"],
                    config.roles["lb_display_not_top"],
                )
                for r in member.roles
            )

            if has_display_opt_in:
                rs.remove(
                    config.roles["lb_display_top_1"],
                    config.roles["lb_display_top_2"],
                    config.roles["lb_display_top_3"],
                    config.roles["lb_display_not_top"],
                )

                if rank:
                    rs.add(DISPLAY_ROLES[rank])
                else:
                    rs.add(DISPLAY_NOT_TOP)


async def update_leaderboard_message(bot, guild: discord.Guild):
    """Update the leaderboard message in the leaderboard channel."""
    from modules import config

    channel = guild.get_channel(config.channels['leaderboard'])
    if not channel:
        return

    ranked_leaderboard = get_ranked_leaderboard(guild)

    lines = ['# __THE LEADERBOARD__', '\n-# ** **']

    for rank_idx, (actual_rank, points, members) in enumerate(ranked_leaderboard):
        if rank_idx >= 15:
            break

        members.sort(key=lambda m: m.display_name.lower())
        member_mentions = ' '.join(member.mention for member in members)

        display_rank = rank_idx + 1
        emoji = LB_EMOJI.get(display_rank, "")

        if display_rank == 1:
            lines.append(f'# {emoji} `{points:3} pts` {member_mentions}')
        elif display_rank == 2:
            lines.append(f'## {emoji} `{points:3} pts` {member_mentions}')
        elif display_rank == 3:
            lines.append(f'### {emoji} `{points:3} pts` {member_mentions}')
        elif display_rank <= 10:
            lines.append(f'{display_rank}. `{points:3} pts` {member_mentions}')
        else:
            lines.append(f'-# {display_rank}. **    **`{points:3} pts` {member_mentions}')

    if len(lines) <= 2:
        lines.append('no one on the leaderboard yet!')

    message_text = '\n'.join(lines)

    bot_message = None
    async for msg in channel.history(limit=10):
        if msg.author == bot.user:
            bot_message = msg
            break

    if bot_message:
        await bot_message.edit(content=message_text, allowed_mentions=discord.AllowedMentions.none())
    else:
        await channel.send(message_text, allowed_mentions=discord.AllowedMentions.none())

    await sync_leaderboard_roles(guild, ranked_leaderboard)
