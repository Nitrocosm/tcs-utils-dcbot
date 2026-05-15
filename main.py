import asyncio

import discord
from discord import VoiceChannel
from discord.ext import commands
from modules import config, activity, moderation, general, badges, verification, logging_config
from modules.config import TARGET_GUILD
from modules.general import timed_delete_msg, send_timed_delete_msg
from modules.role_management import RoleSession
from modules.saves import create_save, disband_save, rename_save
from modules.points import calculate_points, get_ranked_leaderboard, update_leaderboard_message, parse_challenge_role, get_member_rank, has_all_challenges, LB_EMOJI
from modules.bot_init import bot

logging_config.setup()
bot.pings = True

# Cogs are loaded in main() below. Each commit in Phase 2 appends to this list
# as commands/events migrate out of main.py and into cogs/.
EXTENSIONS: list[str] = [
    'cogs.core',
    'cogs.moderation',
    'cogs.activity',
    'cogs.points',
    'cogs.saves',
    'cogs.server_events',
]




# Forum auto-tag mapping is configured in modules/config/ids.py
FORUM_CHANNEL_TAG_IDS = config.FORUM_CHANNEL_TAG_IDS

@bot.event
async def on_thread_create(thread: discord.Thread):
    await asyncio.sleep(1)
    if not isinstance(thread.parent, discord.ForumChannel):
        return
    if thread.parent_id == verification.VERIFICATION_FORUM_ID:
        await verification.start_verification_flow(thread)
        return
    if thread.parent_id not in FORUM_CHANNEL_TAG_IDS:
        return

    tag = thread.parent.get_tag(FORUM_CHANNEL_TAG_IDS[thread.parent_id])
    if tag:
        current_tags = thread.applied_tags
        if tag not in current_tags:
            current_tags.append(tag)
            await thread.edit(applied_tags=current_tags)

    await thread.send(f"<@&{config.roles['verifier']}> new challenge to verify")
    #------------------------------------
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
    Rebuild the custom subsection under `header`.

    This version does not assume there is a pre-existing free slot.
    It assigns the final custom roles to the positions immediately below
    the divider, pushing whatever needs to move.
    """
    divider, existing_custom = _custom_divider_and_roles(guild, header)
    if divider is None:
        raise RuntimeError(
            f"Could not find empty divider in section `{header.name}`"
        )

    # The current custom subsection already occupies these positions.
    # We reuse those positions, and if one of the roles is new/outside the block,
    # Discord will shift positions accordingly when applying the map.
    current_positions_top_to_bottom = [role.position for role in existing_custom]

    if len(final_custom_roles_top_to_bottom) != len(current_positions_top_to_bottom) + 1:
        raise RuntimeError(
            "Internal mismatch while rebuilding custom subsection"
        )

    # Insert the new role by using the divider-adjacent top position and then
    # the remaining existing custom positions below it.
    target_positions_top_to_bottom = [divider.position - 1] + current_positions_top_to_bottom

    position_map = {
        role: pos
        for role, pos in zip(
            final_custom_roles_top_to_bottom,
            target_positions_top_to_bottom,
            strict=True,
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
        errors.append("❌ could not apply colors to the badge role")
    except discord.HTTPException as e:
        errors.append(f"❌ failed to apply colors to the badge role: `{e}`")

    try:
        await _apply_visuals_to_role(
            created_roles["pingable"],
            visuals,
            reason=reason,
        )
    except discord.Forbidden:
        errors.append("❌ could not apply colors to the pingable role")
    except discord.HTTPException as e:
        errors.append(f"❌ failed to apply colors to the pingable role: `{e}`")

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


async def main():
    async with bot:
        for ext in EXTENSIONS:
            await bot.load_extension(ext)
        await bot.start(config.TOKEN)


if __name__ == '__main__':
    asyncio.run(main())