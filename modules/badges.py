import discord
from discord.ui import View, Select
from modules.points import parse_challenge_role, get_ranked_leaderboard, sync_leaderboard_roles
from modules.role_management import RoleSession
from modules import config

WARDROBE_CHANNEL_ID = 1468068634680229979
WARDROBE_CUSTOM_ID = "wardrobe:open"
WARDROBE_MESSAGE_TEXT = (
    "# <:badge_placeholder:1454599839189962783> **badge wardrobe**\n"
    "choose the badge you wish to display near your name!"
)

LEADERBOARD_OPTION_VALUE = "leaderboard_rank"

LEADERBOARD_DISPLAY_ROLES = {
    config.roles["lb_display_top_1"],
    config.roles["lb_display_top_2"],
    config.roles["lb_display_top_3"],
    config.roles["lb_display_not_top"],
}

# -------------------------
# difficulty placeholders
# -------------------------

_DIFFICULTY_PLACEHOLDERS = [
    "<:badge_placeholder_custom_npc:1468336218407436328>",      # 0  – NPC
    "<:badge_placeholder_custom_normal:1468336216171614490>",   # 1  – normal (1-2)
    "<:badge_placeholder_custom_hard:1468336226154184867>",     # 2  – hard (3-4)
    "<:badge_placeholder_custom_insane:1468336205635784988>",   # 3  – insane (5-7)
    "<:badge_placeholder_custom_extreme:1468336223444537414>",  # 4  – extreme (8-10)
    "<:badge_placeholder_custom_brutal:1468336220609314877>",   # 5  – brutal (11-13)
    "<:badge_placeholder_custom_maso:1468336214124925073>",     # 6  – masochistic (14-17)
    "<:badge_placeholder_custom_leg:1468336228914172119>",      # 7  – legendary (18-23)
    "<:badge_placeholder_custom_godlike:1468518569619886111>",  # 8  – godlike (24+)
]


def _points_to_difficulty(points: int) -> int:
    if points <= 0:  return 0
    if points <= 2:  return 1
    if points <= 4:  return 2
    if points <= 7:  return 3
    if points <= 10: return 4
    if points <= 13: return 5
    if points <= 17: return 6
    if points <= 23: return 7
    return 8


def get_challenge_emoji(guild: discord.Guild, name: str, points: int) -> str:
    """Return the badge emoji for a challenge, or a difficulty placeholder."""
    emoji = badge_emoji_for_name(guild, name)
    if emoji:
        return str(emoji)
    return _DIFFICULTY_PLACEHOLDERS[_points_to_difficulty(points)]


# -------------------------
# helpers
# -------------------------

def badge_emoji_for_name(guild: discord.Guild, name: str):
    clean = (
        name.lower()
        .replace("'", "")
        .replace(",", "")
        .replace("!", "")
        .replace("?", "")
        .replace(" ", "_")
        .replace("-", "_")
    )
    return discord.utils.get(guild.emojis, name=f"badge_{clean}")


def get_owned_badge_roles(member: discord.Member):
    guild = member.guild
    roles_by_name = {r.name: r for r in guild.roles}

    owned_badges = set()   # set[discord.Role]
    all_badges = set()     # set[discord.Role]
    badge_points: dict[int, int] = {}  # role_id -> points

    for role in guild.roles:
        info = parse_challenge_role(role)
        if not info:
            continue

        badge_name = f"👁 {info['name']}"
        badge = roles_by_name.get(badge_name)
        if badge:
            all_badges.add(badge)
            badge_points[badge.id] = info['points']
            if role in member.roles:
                owned_badges.add(badge)

    # exceptions
    exceptions = {
        "👑⭐ beat all base challenges": "👁 challenge completion star",
        "👑☄️ beat all ultimate challenges": "👁 pure challenge completion star",
    }

    for challenge_name, badge_name in exceptions.items():
        c = roles_by_name.get(challenge_name)
        b = roles_by_name.get(badge_name)
        if b:
            all_badges.add(b)
            # exceptions are always top-tier; default to godlike placeholder
            badge_points.setdefault(b.id, 24)
            if c and c in member.roles:
                owned_badges.add(b)

    return owned_badges, all_badges, badge_points


def has_leaderboard_opt_in(member: discord.Member) -> bool:
    return any(r.id in LEADERBOARD_DISPLAY_ROLES for r in member.roles)


# -------------------------
# views
# -------------------------

class WardrobeOpenView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="open wardrobe",
        style=discord.ButtonStyle.secondary,  # type: ignore
        emoji="🥇",
        custom_id=WARDROBE_CUSTOM_ID,
    )
    async def open(self, interaction: discord.Interaction, _):
        member = interaction.user
        owned, _, _ = get_owned_badge_roles(member)

        if not owned and not has_leaderboard_opt_in(member):
            return await interaction.response.send_message(  # type: ignore
                "you don’t own any badges yet - complete challenges to unlock them!",
                ephemeral=True,
            )

        return await interaction.response.send_message(  # type: ignore
            "pick a badge to display:",
            view=WardrobeSelectView(member),
            ephemeral=True,
        )


BADGES_PER_PAGE = 23  # 23 badges + 2 fixed options = 25 max

class WardrobeSelectView(View):
    def __init__(self, member: discord.Member, page: int = 0):
        super().__init__(timeout=60)
        self.member = member
        self.page = page

        owned, _, badge_points = get_owned_badge_roles(member)
        self.sorted_badges = sorted(owned, key=lambda r: r.position, reverse=True)
        self.total_pages = max(1, -(-len(self.sorted_badges) // BADGES_PER_PAGE))  # ceil div

        fixed_options = [
            discord.SelectOption(label="none", description="remove displayed badge", value="none", emoji="🚫"),
            discord.SelectOption(label="leaderboard rank", description="show a medal if you're on top-3, show nothing otherwise", value=LEADERBOARD_OPTION_VALUE, emoji="🏆"),
        ]

        start = page * BADGES_PER_PAGE
        page_badges = self.sorted_badges[start:start + BADGES_PER_PAGE]

        options = fixed_options if page == 0 else []
        for badge in page_badges:
            badge_display_name = badge.name.replace("👁 ", "")
            pts = badge_points.get(badge.id, 0)
            raw_emoji = badge_emoji_for_name(member.guild, badge_display_name)
            if raw_emoji:
                select_emoji = raw_emoji
            else:
                difficulty = _points_to_difficulty(pts)
                placeholder_str = _DIFFICULTY_PLACEHOLDERS[difficulty]
                import re as _re
                m = _re.match(r"<:(\w+):(\d+)>", placeholder_str)
                select_emoji = discord.PartialEmoji(name=m.group(1), id=int(m.group(2))) if m else None
            options.append(discord.SelectOption(
                label=badge.name.replace("👁 ", ""),
                value=str(badge.id),
                emoji=select_emoji,
            ))

        self.add_item(WardrobeSelect(options=options))

        if self.total_pages > 1:
            prev_btn = discord.ui.Button(label="◀ prev", style=discord.ButtonStyle.secondary, disabled=(page == 0))
            next_btn = discord.ui.Button(label="next ▶", style=discord.ButtonStyle.secondary, disabled=(page >= self.total_pages - 1))

            async def prev_callback(interaction: discord.Interaction):
                await interaction.response.edit_message(view=WardrobeSelectView(member, page - 1))  # type: ignore

            async def next_callback(interaction: discord.Interaction):
                await interaction.response.edit_message(view=WardrobeSelectView(member, page + 1))  # type: ignore

            prev_btn.callback = prev_callback
            next_btn.callback = next_callback
            self.add_item(prev_btn)
            self.add_item(next_btn)

class WardrobeSelect(Select):
    async def callback(self, interaction: discord.Interaction):
        member = interaction.user
        _, all_badges, _ = get_owned_badge_roles(member)

        choice = self.values[0]

        async with RoleSession(member) as rs:
            # remove all normal badge display roles
            for badge in all_badges:
                rs.remove(badge.id)

            # remove all leaderboard display roles
            for r_id in LEADERBOARD_DISPLAY_ROLES:
                rs.remove(r_id)

            if choice == LEADERBOARD_OPTION_VALUE:
                # opt-in to leaderboard display
                rs.add(config.roles["lb_display_not_top"])

            elif choice != "none":
                rs.add(int(choice))

        if choice == "none":
            text = "badge removed ✅"
        elif choice == LEADERBOARD_OPTION_VALUE:
            text = (
                "you're now showing your leaderboard rank 🏆\n"
                "updates automatically if you're top 3"
            )
        else:
            text = "done, badge updated, go show it off ✨"

        await interaction.response.edit_message(  # type: ignore
            content=text,
            view=None,
        )

        ranked_leaderboard = get_ranked_leaderboard(member.guild)
        await sync_leaderboard_roles(member.guild, ranked_leaderboard)


# -------------------------
# setup
# -------------------------

async def ensure_wardrobe_message(bot: discord.Client):
    guild = bot.get_guild(config.TARGET_GUILD)
    channel = guild.get_channel(WARDROBE_CHANNEL_ID)
    if not channel:
        return

    async for msg in channel.history(limit=25):
        if msg.author == bot.user and msg.components:
            for row in msg.components:
                for c in row.children:
                    if getattr(c, "custom_id", None) == WARDROBE_CUSTOM_ID:
                        return

    await channel.send(
        WARDROBE_MESSAGE_TEXT,
        view=WardrobeOpenView(),
        allowed_mentions=discord.AllowedMentions.none(),
    )