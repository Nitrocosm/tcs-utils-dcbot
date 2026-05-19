"""Bootstrap a staging Discord server for smoke-testing the refactored bot.

Creates every role, channel, thread, forum, forum-tag, and message that the
bot's hardcoded IDs reference. Idempotent — re-running is safe; existing
entities are reused (matched by name). After it finishes, writes a complete
``modules/config/ids_staging.py`` with all the discovered/created IDs.

Custom emojis are mapped to Unicode placeholders (this server won't look as
pretty as TCS, but every code path that touches emoji will function).

To use the generated file:

    1. set ``STAGING_IDS=1`` in your .env (or shell env)
    2. modules/config/__init__.py picks ``ids_staging.py`` automatically
       (see the small swap at the bottom of this file's docstring)

Usage:
    .venv/Scripts/python scripts/setup_staging.py <staging_guild_id>

Requires the bot to be in the guild with Administrator (or at minimum:
Manage Roles, Manage Channels, Send Messages, Add Reactions).
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import discord  # noqa: E402
from dotenv import load_dotenv  # noqa: E402


load_dotenv()
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    sys.exit("ERROR: TOKEN missing from .env")

# Optional. If set, gets baked into ids_staging.py so owner-only commands work
# without a follow-up hand edit. Read either from .env or shell env.
STAGING_OWNER_ID = int(os.getenv("STAGING_OWNER_ID") or 0)

if len(sys.argv) < 2:
    sys.exit(f"usage: {sys.argv[0]} <staging_guild_id>")

try:
    STAGING_GUILD_ID = int(sys.argv[1])
except ValueError:
    sys.exit("staging_guild_id must be an integer")


# ── Entity plan ─────────────────────────────────────────────────────────────
# Each plain role gets a name == its config key.
# Category roles (the ones referenced inside new_people / role_check arrays)
# use the bot's expected `──╱ <name> ─` pattern so _get_role_hierarchy() finds
# them. "none" markers use the exact name the bot expects: `🚫 none`.

CATEGORY_ROLE_NAMES = {
    "cat_activity": "──╱ activity ─",
    "cat_common":   "──╱ common ─",
    "cat_badges":   "──╱ badges ─",
    "cat_misc":     "──╱ misc ─",
}

# new_people order matters — keep the same order TCS uses
NEW_PEOPLE_PLAN: list[tuple[str, str]] = [
    ("cat_activity",       CATEGORY_ROLE_NAMES["cat_activity"]),
    ("not_available_seed", "not_available"),     # placeholder for not_available role
    ("cat_common",         CATEGORY_ROLE_NAMES["cat_common"]),
    ("newbie_seed",        "newbie"),
    ("person_seed",        "person"),
    ("cat_badges",         CATEGORY_ROLE_NAMES["cat_badges"]),
    ("none_badges",        "🚫 none"),
    ("cat_misc",           CATEGORY_ROLE_NAMES["cat_misc"]),
    ("none_misc",          "🚫 none"),
]

# Scalar role keys → desired role name on staging
SCALAR_ROLES: dict[str, str] = {
    "bot": "bot",
    "leader": "leader",
    "in_vc_leader": "in_vc_leader",
    "in_vc_2_leader": "in_vc_2_leader",
    "in_vc_3_leader": "in_vc_3_leader",
    "in_vc": "in_vc",
    "in_vc_2": "in_vc_2",
    "in_vc_3": "in_vc_3",
    "available_leader": "available_leader",
    "available": "available",
    "available_not_in_vc": "available_not_in_vc",
    "available_not_in_vc_2": "available_not_in_vc_2",
    "available_not_in_vc_3": "available_not_in_vc_3",
    "not_available": "not_available",
    "birthday": "birthday",
    "inactive": "inactive",
    "explained_inactive": "explained_inactive",
    "person": "person",
    "newbie": "newbie",
    "warn_1": "warn_1",
    "warn_2": "warn_2",
    "warn_3": "warn_3",
    "mod": "mod",
    "spoiler": "spoiler",
    "verifier": "verifier",
    "alts": "alts",
    "lb_display_top_1": "lb_display_top_1",
    "lb_display_top_2": "lb_display_top_2",
    "lb_display_top_3": "lb_display_top_3",
    "lb_display_not_top": "lb_display_not_top",
    "lb_top_1": "lb_top_1",
    "lb_top_2": "lb_top_2",
    "lb_top_3": "lb_top_3",
    "completion_all_base": "completion_all_base",
    "completion_all_ultimate": "completion_all_ultimate",
}

# admins array — list of role NAMES (you can populate with extras later)
ADMINS_PLAN = ["admin_owner", "admin_mod"]   # second one will be aliased to roles['mod']

# role_check array — these reference category roles, same as new_people uses
ROLE_CHECK_PLAN_KEYS = ["cat_activity", "cat_common", "cat_badges", "cat_misc"]


# Channels — kind in {"text", "voice", "forum"}
CHANNELS_PLAN: list[tuple[str, str, str]] = [
    ("vc",                 "vc",                  "voice"),
    ("vc2",                "vc-2",                "voice"),
    ("vc3",                "vc-3",                "voice"),
    ("chat",               "chat",                "text"),
    ("availability",       "availability",        "text"),
    ("ps_link",            "ps-link",             "text"),
    ("best_runs",          "best-runs",           "text"),
    ("mod_chat",           "mod-chat",            "text"),
    ("leader_chat",        "leader-chat",         "text"),
    ("logs_channel",       "logs",                "text"),
    ("spoiler",            "spoiler",             "text"),
    ("spoiler_access",     "spoiler-access",      "text"),
    ("leaderboard",        "leaderboard",         "text"),
]

# Special channels owned by module-level constants in the codebase
SPECIAL_TEXT_CHANNELS: list[tuple[str, str]] = [
    ("VERIFICATION_FORUM_ID", "verification"),       # actually a forum, handled below
    ("RELATIONS_CHANNEL_ID",  "role-relations"),
    ("WARDROBE_CHANNEL_ID",   "wardrobe"),
]

# Forum channels (key in the FORUM_CHANNEL_TAG_IDS dict). For staging we'll
# create them with one tag each.
FORUM_TAG_PLAN: list[tuple[str, str, str]] = [
    ("forum_alpha", "forum-alpha", "alpha-tag"),
    ("forum_beta",  "forum-beta",  "beta-tag"),
]


# Thread (lives inside chat channel)
THREADS_PLAN: list[tuple[str, str, str]] = [
    ("challenge_log_thread", "challenge-log", "chat"),  # name, parent channel key
]


# Messages to post + react. message_key -> (channel_key, content, [reactions])
MESSAGES_PLAN: dict[str, tuple[str, str, list[str]]] = {
    "availability_message": (
        "availability",
        "react with the available emoji to mark yourself as available",
        ["✅"],
    ),
    "reaction_roles_spoiler": (
        "spoiler_access",
        "react with ⚠️ to opt into spoiler content",
        ["⚠️"],
    ),
    "INTERESTED_MESSAGE_BASE": (
        "availability",
        "react below to be pinged for **base** challenge runs",
        ["🟢"],
    ),
    "INTERESTED_MESSAGE_STAR": (
        "availability",
        "react below to be pinged for **star** challenge runs",
        ["⭐"],
    ),
    "INTERESTED_MESSAGE_ULTIMATE": (
        "availability",
        "react below to be pinged for **ultimate** challenge runs",
        ["☄️"],
    ),
}


# Custom-emoji → Unicode placeholder mapping. Used inside the generated
# ids_staging.py's emoji dict so the bot's message templates never reference
# missing custom emojis.
STAGING_EMOJI_MAP: dict[str, str] = {
    "join": "👋", "leave": "👋",
    "ban": "🔨", "kick": "🦵",
    "app_join": "📥", "app_leave": "📤",
    "available": "✅", "unavailable": "❌",
    "join_vc": "🔊", "leave_vc": "🔇",
    "join_vc_2": "🔊", "leave_vc_2": "🔇",
    "join_vc_3": "🔊",
    "promotion": "⬆️", "demotion": "⬇️",
    "birthday": "🎂", "leader": "👑",
    "death": "💀", "disconnect": "🔌",
    "blank": "⬛",
    "tcs": "🏆", "gor": "🏆", "pdo": "🏆", "nn": "🏆",
    "edit": "✏️", "edit_g": "✏️", "edit_p": "✏️", "edit_r": "✏️",
    "newbie": "🆕",
    "inactive": "🛌", "inactive_revoke": "🏆", "explained_inactive": "✅",
    "knife": "🔪", "hug": "🤗", "kiss": "💋",
    "high_five": "✋", "handshake": "🤝",
    "fire": "🔥", "punch": "👊", "slap": "👋",
    "pat": "🫳", "touch": "👉",
    "lb_top_1": "🥇", "lb_top_2": "🥈", "lb_top_3": "🥉",
    "star_completion": "⭐", "star_pure_completion": "🌟",
}

# Digit emojis (used by general.emojify). Same Unicode regardless of colour suffix.
UNICODE_DIGITS = ["0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]


# ── Discord runtime ─────────────────────────────────────────────────────────


class Setup:
    def __init__(self, guild: discord.Guild):
        self.guild = guild
        self.created: list[str] = []
        self.reused: list[str] = []

        # populated as we go
        self.role_ids: dict[str, int] = {}      # plan-key → role.id
        self.channel_ids: dict[str, int] = {}   # plan-key → channel.id
        self.message_ids: dict[str, int] = {}   # plan-key → message.id

    def log(self, msg: str) -> None:
        print(msg)

    async def get_or_create_role(self, key: str, name: str, **kwargs) -> discord.Role:
        existing = discord.utils.get(self.guild.roles, name=name)
        if existing:
            self.reused.append(f"role:{name}")
            self.role_ids[key] = existing.id
            self.log(f"  [reuse] role {name!r} (id={existing.id})")
            return existing
        try:
            role = await self.guild.create_role(name=name, **kwargs)
        except discord.Forbidden:
            sys.exit(f"FATAL: bot lacks Manage Roles to create {name!r}")
        self.created.append(f"role:{name}")
        self.role_ids[key] = role.id
        self.log(f"  [new]   role {name!r} (id={role.id})")
        return role

    async def get_or_create_text_channel(self, key: str, name: str) -> discord.TextChannel:
        existing = discord.utils.get(self.guild.text_channels, name=name)
        if existing:
            self.reused.append(f"text:{name}")
            self.channel_ids[key] = existing.id
            self.log(f"  [reuse] #{name} (id={existing.id})")
            return existing
        try:
            ch = await self.guild.create_text_channel(name=name)
        except discord.Forbidden:
            sys.exit(f"FATAL: bot lacks Manage Channels to create #{name}")
        self.created.append(f"text:{name}")
        self.channel_ids[key] = ch.id
        self.log(f"  [new]   #{name} (id={ch.id})")
        return ch

    async def get_or_create_voice_channel(self, key: str, name: str) -> discord.VoiceChannel:
        existing = discord.utils.get(self.guild.voice_channels, name=name)
        if existing:
            self.reused.append(f"voice:{name}")
            self.channel_ids[key] = existing.id
            self.log(f"  [reuse] #{name} (voice) (id={existing.id})")
            return existing
        try:
            ch = await self.guild.create_voice_channel(name=name)
        except discord.Forbidden:
            sys.exit(f"FATAL: bot lacks Manage Channels to create #{name}")
        self.created.append(f"voice:{name}")
        self.channel_ids[key] = ch.id
        self.log(f"  [new]   #{name} (voice) (id={ch.id})")
        return ch

    async def get_or_create_forum(self, key: str, name: str, tag_name: str) -> tuple[discord.ForumChannel, int]:
        existing = discord.utils.get(self.guild.forums, name=name) if hasattr(self.guild, "forums") else None
        if existing is None:
            existing = next(
                (c for c in self.guild.channels if isinstance(c, discord.ForumChannel) and c.name == name),
                None,
            )
        if existing is None:
            try:
                existing = await self.guild.create_forum(name=name)
            except discord.Forbidden:
                sys.exit(f"FATAL: bot lacks Manage Channels to create forum #{name}")
            self.created.append(f"forum:{name}")
            self.log(f"  [new]   forum #{name} (id={existing.id})")
        else:
            self.reused.append(f"forum:{name}")
            self.log(f"  [reuse] forum #{name} (id={existing.id})")
        self.channel_ids[key] = existing.id

        # tag
        tag_obj = next((t for t in existing.available_tags if t.name == tag_name), None)
        if tag_obj is None:
            new_tag = discord.ForumTag(name=tag_name)
            new_tags = list(existing.available_tags) + [new_tag]
            await existing.edit(available_tags=new_tags)
            # re-fetch the tag with its assigned id
            existing = self.guild.get_channel(existing.id)  # type: ignore
            tag_obj = next((t for t in existing.available_tags if t.name == tag_name), None)
            self.created.append(f"tag:{name}/{tag_name}")
            self.log(f"  [new]   tag :{tag_name}: on #{name} (id={tag_obj.id})")
        else:
            self.reused.append(f"tag:{name}/{tag_name}")
            self.log(f"  [reuse] tag :{tag_name}: on #{name} (id={tag_obj.id})")
        return existing, tag_obj.id  # type: ignore

    async def get_or_create_thread(self, key: str, name: str, parent_channel: discord.TextChannel) -> discord.Thread:
        # check active + archived threads
        for t in parent_channel.threads:
            if t.name == name:
                self.reused.append(f"thread:{name}")
                self.channel_ids[key] = t.id
                self.log(f"  [reuse] thread {name!r} (id={t.id})")
                return t
        async for t in parent_channel.archived_threads(limit=100):
            if t.name == name:
                self.reused.append(f"thread:{name}")
                self.channel_ids[key] = t.id
                self.log(f"  [reuse] thread {name!r} (archived, id={t.id})")
                return t
        # create a starter message and convert into a thread
        thread = await parent_channel.create_thread(
            name=name, type=discord.ChannelType.public_thread
        )
        self.created.append(f"thread:{name}")
        self.channel_ids[key] = thread.id
        self.log(f"  [new]   thread {name!r} (id={thread.id})")
        return thread

    async def get_or_create_message(
        self,
        key: str,
        channel: discord.TextChannel,
        content: str,
        reactions: list[str],
    ) -> discord.Message:
        # heuristic: look in channel.history for a message authored by the bot
        # whose content starts with the same prefix
        prefix = content[:50]
        async for msg in channel.history(limit=100):
            if msg.author.id == self.guild.me.id and msg.content.startswith(prefix):
                self.reused.append(f"msg:{key}")
                self.message_ids[key] = msg.id
                self.log(f"  [reuse] msg {key!r} in #{channel.name} (id={msg.id})")
                # make sure reactions are present
                existing_reactions = {str(r.emoji) for r in msg.reactions}
                for emoji in reactions:
                    if emoji not in existing_reactions:
                        await msg.add_reaction(emoji)
                return msg

        msg = await channel.send(content)
        for emoji in reactions:
            await msg.add_reaction(emoji)
        self.created.append(f"msg:{key}")
        self.message_ids[key] = msg.id
        self.log(f"  [new]   msg {key!r} in #{channel.name} (id={msg.id})")
        return msg


async def run(setup: Setup):
    g = setup.guild
    print(f"\nstaging guild: {g.name} ({g.id})\n")

    # ── roles ───────────────────────────────────────────────────────────────
    print("== ROLES ==")

    # new_people (in order)
    new_people_ids: list[int] = []
    for plan_key, name in NEW_PEOPLE_PLAN:
        # for the seeds, reuse the matching scalar role later — but ensure it exists now
        role = await setup.get_or_create_role(plan_key, name)
        new_people_ids.append(role.id)

    # scalar roles
    for key, name in SCALAR_ROLES.items():
        # if a role with this name was already created above, reuse it
        existing = discord.utils.get(g.roles, name=name)
        if existing:
            setup.role_ids[key] = existing.id
            setup.reused.append(f"role:{name}")
            setup.log(f"  [reuse] role {name!r} (id={existing.id})  [alias for {key}]")
        else:
            await setup.get_or_create_role(key, name)

    # admins
    admin_ids: list[int] = []
    for name in ADMINS_PLAN:
        existing = discord.utils.get(g.roles, name=name)
        if existing:
            admin_ids.append(existing.id)
            setup.reused.append(f"role:{name}")
            setup.log(f"  [reuse] role {name!r} (id={existing.id})  [admins]")
        else:
            role = await g.create_role(name=name)
            admin_ids.append(role.id)
            setup.created.append(f"role:{name}")
            setup.log(f"  [new]   role {name!r} (id={role.id})  [admins]")

    role_check_ids = [setup.role_ids[k] for k in ROLE_CHECK_PLAN_KEYS]

    # ── channels ────────────────────────────────────────────────────────────
    print("\n== CHANNELS ==")
    for key, name, kind in CHANNELS_PLAN:
        if kind == "text":
            await setup.get_or_create_text_channel(key, name)
        elif kind == "voice":
            await setup.get_or_create_voice_channel(key, name)

    # ── special module-level channels ───────────────────────────────────────
    print("\n== SPECIAL CHANNELS ==")
    await setup.get_or_create_text_channel("RELATIONS_CHANNEL_ID", "role-relations")
    await setup.get_or_create_text_channel("WARDROBE_CHANNEL_ID", "wardrobe")

    # VERIFICATION_FORUM_ID is actually a forum channel — handled below

    # ── forums ──────────────────────────────────────────────────────────────
    print("\n== FORUMS ==")
    await setup.get_or_create_forum("VERIFICATION_FORUM_ID", "verification", "verifying")

    forum_tag_pairs: list[tuple[int, int]] = []  # (forum_id, tag_id)
    for key, fname, tname in FORUM_TAG_PLAN:
        forum, tag_id = await setup.get_or_create_forum(key, fname, tname)
        forum_tag_pairs.append((forum.id, tag_id))

    # ── threads ─────────────────────────────────────────────────────────────
    print("\n== THREADS ==")
    for key, name, parent_key in THREADS_PLAN:
        parent = setup.guild.get_channel(setup.channel_ids[parent_key])
        await setup.get_or_create_thread(key, name, parent)  # type: ignore

    # ── messages + reactions ────────────────────────────────────────────────
    print("\n== MESSAGES ==")
    for key, (ch_key, content, reactions) in MESSAGES_PLAN.items():
        ch = setup.guild.get_channel(setup.channel_ids[ch_key])
        await setup.get_or_create_message(key, ch, content, reactions)  # type: ignore

    # ── emit ids_staging.py ─────────────────────────────────────────────────
    print("\n== WRITING modules/config/ids_staging.py ==")
    write_ids_file(setup, admin_ids, new_people_ids, role_check_ids, forum_tag_pairs)

    # ── summary ─────────────────────────────────────────────────────────────
    print(f"\nDone. created={len(setup.created)}, reused={len(setup.reused)}")
    print("\nNext steps:")
    print("  1. set TARGET_GUILD in modules/config/settings.py to your staging guild id, OR")
    print("     export STAGING_GUILD_ID and adjust settings.py to read from env")
    print("  2. swap ids.py for ids_staging.py — edit modules/config/__init__.py:")
    print("        from .ids_staging import roles, channels, emoji, OWNER_ID,")
    print("                                  REACTION_ROLES, FORUM_CHANNEL_TAG_IDS")
    print("     (or use the STAGING_IDS env var hook if you added one)")
    print("  3. run scripts/preflight.py — every row should now be [OK]")
    print("  4. boot the bot and run through SMOKE_TEST.md")


def write_ids_file(
    setup: Setup,
    admin_ids: list[int],
    new_people_ids: list[int],
    role_check_ids: list[int],
    forum_tag_pairs: list[tuple[int, int]],
):
    rids = setup.role_ids
    cids = setup.channel_ids
    mids = setup.message_ids
    owner_comment = "" if STAGING_OWNER_ID else "   # FIXME: set to your Discord user id for owner-only commands"

    lines: list[str] = []
    L = lines.append
    L('"""Staging-server IDs. Generated by scripts/setup_staging.py.')
    L("")
    L("Mirrors the surface of ids.py with snowflakes from a staging guild.")
    L("Custom emojis are mapped to Unicode placeholders.")
    L("")
    L("Set STAGING_IDS=1 in .env to make modules/config/__init__.py load this file.")
    L('"""')
    L("")
    L("roles = {")
    L(f"    'admins': {admin_ids!r},")
    L(f"    'new_people': {new_people_ids!r},")
    L(f"    'role_check': {role_check_ids!r},")
    L("")
    scalar_keys = [
        "bot", "leader",
        "in_vc_leader", "in_vc_2_leader", "in_vc_3_leader",
        "in_vc", "in_vc_2", "in_vc_3",
        "available_leader", "available",
        "available_not_in_vc", "available_not_in_vc_2", "available_not_in_vc_3",
        "not_available",
        "birthday", "inactive", "explained_inactive", "person", "newbie",
        "warn_1", "warn_2", "warn_3", "mod", "spoiler", "verifier", "alts",
        "lb_display_top_1", "lb_display_top_2", "lb_display_top_3", "lb_display_not_top",
        "lb_top_1", "lb_top_2", "lb_top_3",
        "completion_all_base", "completion_all_ultimate",
    ]
    for key in scalar_keys:
        L(f"    {key!r}: {rids.get(key, 0)},")
    L("}")
    L("")
    L("")
    L("channels = {")
    chan_pairs = [
        ("vc", cids.get("vc", 0)),
        ("vc2", cids.get("vc2", 0)),
        ("vc3", cids.get("vc3", 0)),
        ("chat", cids.get("chat", 0)),
        ("availability", cids.get("availability", 0)),
        ("availability_message", mids.get("availability_message", 0)),
        ("availability_reaction", 0),  # placeholder — Unicode emoji used instead
        ("ps_link", cids.get("ps_link", 0)),
        ("best_runs", cids.get("best_runs", 0)),
        ("mod_chat", cids.get("mod_chat", 0)),
        ("leader_chat", cids.get("leader_chat", 0)),
        ("logs_channel", cids.get("logs_channel", 0)),
        ("spoiler", cids.get("spoiler", 0)),
        ("spoiler_access", cids.get("spoiler_access", 0)),
        ("spoiler_role", rids.get("spoiler", 0)),
        ("leaderboard", cids.get("leaderboard", 0)),
        ("challenge_log_thread", cids.get("challenge_log_thread", 0)),
    ]
    for key, val in chan_pairs:
        L(f"    {key!r}: {val},")
    L("}")
    L("")
    L("")
    L("emoji = {")
    for key, val in STAGING_EMOJI_MAP.items():
        L(f"    {key!r}: {val!r},")
    for i, glyph in enumerate(UNICODE_DIGITS):
        L(f"    {str(i)!r}: {glyph!r},")
    for color in ["b", "g", "p", "r"]:
        for i, glyph in enumerate(UNICODE_DIGITS):
            L(f"    {(str(i) + color)!r}: {glyph!r},")
    L("}")
    L("")
    L("")
    L(f"OWNER_ID = {STAGING_OWNER_ID}{owner_comment}")
    L("")
    L("")
    L("REACTION_ROLES = {")
    L(f"    {mids.get('reaction_roles_spoiler', 0)}: {{")
    L(f"        '⚠️': {rids.get('spoiler', 0)},")
    L("    },")
    L("}")
    L("")
    L("")
    L("FORUM_CHANNEL_TAG_IDS = {")
    for fid, tid in forum_tag_pairs:
        L(f"    {fid}: {tid},")
    L("}")
    L("")

    text = "\n".join(lines)
    out = Path("modules/config/ids_staging.py")
    out.write_text(text, encoding="utf-8")
    print(f"  wrote {out} ({len(text)} bytes)")


def main():
    intents = discord.Intents.default()
    intents.members = True
    intents.guilds = True
    intents.message_content = True
    client = discord.Client(intents=intents)

    exit_code = {"v": 1}

    @client.event
    async def on_ready():
        try:
            guild = client.get_guild(STAGING_GUILD_ID)
            if guild is None:
                print(f"FATAL: bot is not in guild {STAGING_GUILD_ID}")
                exit_code["v"] = 1
                return
            setup = Setup(guild)
            await run(setup)
            exit_code["v"] = 0
        except Exception as e:
            print(f"FATAL: {e!r}")
            raise
        finally:
            await client.close()

    client.run(TOKEN, log_handler=None)
    sys.exit(exit_code["v"])


if __name__ == "__main__":
    asyncio.run(asyncio.sleep(0))  # warm asyncio policy on Windows
    main()
