"""Preflight check — verify the bot can see every ID it'll touch at runtime.

Run before booting the bot for a smoke test. Connects with minimal intents,
checks every role / channel / message / thread the codebase references,
prints a result table, and exits.

Usage:
    .venv/Scripts/python scripts/preflight.py

Reads TOKEN from .env (same as the bot). Does NOT load any cogs and does
NOT register any event listeners — read-only inspection only.
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

# allow running from repo root: `python scripts/preflight.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import discord  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from modules import config  # noqa: E402
from modules.activity import (  # noqa: E402
    INTERESTED_MESSAGE_BASE,
    INTERESTED_MESSAGE_STAR,
    INTERESTED_MESSAGE_ULTIMATE,
)
from modules.badges import WARDROBE_CHANNEL_ID  # noqa: E402
from modules.role_management import RELATIONS_CHANNEL_ID  # noqa: E402
from modules.verification import VERIFICATION_FORUM_ID  # noqa: E402

load_dotenv()
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    sys.exit("ERROR: TOKEN missing — copy .env.example to .env and fill it in")

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("preflight")

OK = "PASS"
FAIL = "FAIL"
SKIP = "skip"


class Reporter:
    """Collects pass/fail rows and prints a tidy summary at the end."""

    def __init__(self):
        self.rows: list[tuple[str, str, str, str]] = []

    def record(self, status: str, kind: str, name: str, detail: str = "") -> None:
        self.rows.append((status, kind, name, detail))

    def print_summary(self) -> int:
        kind_w = max(len(r[1]) for r in self.rows)
        name_w = max(len(r[2]) for r in self.rows)
        fails = 0
        for status, kind, name, detail in self.rows:
            mark = "[OK]  " if status == OK else ("[FAIL]" if status == FAIL else "[skip]")
            if status == FAIL:
                fails += 1
            line = f"{mark} {kind:<{kind_w}}  {name:<{name_w}}"
            if detail:
                line += f"  {detail}"
            print(line)
        print()
        total = len(self.rows)
        passes = sum(1 for r in self.rows if r[0] == OK)
        skips = sum(1 for r in self.rows if r[0] == SKIP)
        print(f"Summary: {passes} pass, {fails} fail, {skips} skip  ({total} total)")
        return fails


def check_role(reporter: Reporter, guild: discord.Guild, key: str, role_id: int) -> None:
    role = guild.get_role(role_id)
    if role is None:
        reporter.record(FAIL, "role", key, f"id={role_id} not found in guild")
    else:
        reporter.record(OK, "role", key, f"#{role.name}")


def check_channel(reporter: Reporter, guild: discord.Guild, key: str, channel_id: int) -> discord.abc.GuildChannel | None:
    channel = guild.get_channel(channel_id)
    if channel is None:
        # might be a thread
        thread = guild.get_thread(channel_id)
        if thread is None:
            reporter.record(FAIL, "channel", key, f"id={channel_id} not found")
            return None
        reporter.record(OK, "thread", key, f"#{thread.name} (in #{thread.parent.name if thread.parent else '?'})")
        return thread
    reporter.record(OK, "channel", key, f"#{channel.name} ({type(channel).__name__})")
    return channel


async def check_message(reporter: Reporter, channel, label: str, message_id: int) -> None:
    if channel is None:
        reporter.record(SKIP, "message", label, "(parent channel missing)")
        return
    try:
        msg = await channel.fetch_message(message_id)
        reporter.record(OK, "message", label, f"author=@{msg.author.name}  in #{channel.name}")
    except discord.NotFound:
        reporter.record(FAIL, "message", label, f"id={message_id} not in #{channel.name}")
    except discord.Forbidden:
        reporter.record(FAIL, "message", label, f"id={message_id} (no read access to #{channel.name})")
    except discord.HTTPException as e:
        reporter.record(FAIL, "message", label, f"id={message_id} HTTP error: {e}")


async def check_forum_tag(reporter: Reporter, guild: discord.Guild, forum_id: int, tag_id: int) -> None:
    forum = guild.get_channel(forum_id)
    if forum is None:
        reporter.record(FAIL, "forum", f"forum:{forum_id}", "channel not found")
        return
    if not isinstance(forum, discord.ForumChannel):
        reporter.record(FAIL, "forum", f"#{forum.name}", f"is {type(forum).__name__}, not ForumChannel")
        return
    tag = forum.get_tag(tag_id)
    if tag is None:
        reporter.record(FAIL, "forum_tag", f"#{forum.name}", f"tag {tag_id} not configured on this forum")
    else:
        reporter.record(OK, "forum_tag", f"#{forum.name}", f"tag :{tag.name}:")


async def run_checks(client: discord.Client) -> int:
    reporter = Reporter()

    print(f"\nGuild lookup: TARGET_GUILD={config.TARGET_GUILD}")
    guild = client.get_guild(config.TARGET_GUILD)
    if guild is None:
        print(f"FATAL: bot is not in guild {config.TARGET_GUILD}. Invite it first.")
        return 1
    print(f"  -> {guild.name} ({guild.member_count} members)\n")

    # ── owner ───────────────────────────────────────────────────────────────
    owner = guild.get_member(config.OWNER_ID)
    if owner is None:
        reporter.record(FAIL, "user", "OWNER_ID", f"id={config.OWNER_ID} not in guild")
    else:
        reporter.record(OK, "user", "OWNER_ID", f"@{owner.name}")

    # ── roles ───────────────────────────────────────────────────────────────
    for key, val in config.roles.items():
        if isinstance(val, list):
            for i, rid in enumerate(val):
                check_role(reporter, guild, f"{key}[{i}]", rid)
        else:
            check_role(reporter, guild, key, val)

    # ── channels (most are real channels; some keys hold message/role/emoji ids) ──
    SPECIAL = {
        "availability_message",   # message id inside #availability
        "availability_reaction",  # custom emoji id
        "spoiler_role",           # actually a role id, mis-keyed under channels
    }
    channels_by_key: dict[str, discord.abc.GuildChannel | None] = {}
    for key, cid in config.channels.items():
        if key in SPECIAL:
            continue
        channels_by_key[key] = check_channel(reporter, guild, key, cid)

    # availability_message lives inside the availability channel
    await check_message(
        reporter,
        channels_by_key.get("availability"),
        "availability_message",
        config.channels["availability_message"],
    )

    # availability_reaction is a custom-emoji id; check it's present in the guild
    react_emoji_id = config.channels["availability_reaction"]
    emoji = discord.utils.get(guild.emojis, id=react_emoji_id)
    if emoji is None:
        reporter.record(FAIL, "emoji", "availability_reaction", f"id={react_emoji_id} not in guild emoji")
    else:
        reporter.record(OK, "emoji", "availability_reaction", f":{emoji.name}:")

    # spoiler_role is a role id under the channels dict (legacy naming)
    check_role(reporter, guild, "channels.spoiler_role", config.channels["spoiler_role"])

    # ── module-level IDs ────────────────────────────────────────────────────
    check_channel(reporter, guild, "VERIFICATION_FORUM_ID", VERIFICATION_FORUM_ID)
    check_channel(reporter, guild, "RELATIONS_CHANNEL_ID", RELATIONS_CHANNEL_ID)
    check_channel(reporter, guild, "WARDROBE_CHANNEL_ID", WARDROBE_CHANNEL_ID)

    # ── reaction-roles message ──────────────────────────────────────────────
    # The message_id -> {emoji: role_id} table. We don't know which channel each
    # message lives in; we'll attempt to fetch via every channel we can read.
    for msg_id, mapping in config.REACTION_ROLES.items():
        found = False
        for channel in guild.text_channels:
            try:
                await channel.fetch_message(msg_id)
                reporter.record(OK, "react_roles", f"msg:{msg_id}", f"in #{channel.name} ({len(mapping)} mapping(s))")
                found = True
                break
            except (discord.NotFound, discord.Forbidden):
                continue
        if not found:
            reporter.record(FAIL, "react_roles", f"msg:{msg_id}", "not found in any visible channel")

    # ── interested-role messages (each in #availability) ────────────────────
    for label, mid in [
        ("INTERESTED_MESSAGE_BASE", INTERESTED_MESSAGE_BASE),
        ("INTERESTED_MESSAGE_STAR", INTERESTED_MESSAGE_STAR),
        ("INTERESTED_MESSAGE_ULTIMATE", INTERESTED_MESSAGE_ULTIMATE),
    ]:
        # try common locations
        candidates = [channels_by_key.get("availability"), channels_by_key.get("chat")]
        found = False
        for ch in candidates:
            if ch is None:
                continue
            try:
                await ch.fetch_message(mid)
                reporter.record(OK, "interested_msg", label, f"in #{ch.name}")
                found = True
                break
            except (discord.NotFound, discord.Forbidden):
                continue
        if not found:
            # fall back: any text channel
            for channel in guild.text_channels:
                try:
                    await channel.fetch_message(mid)
                    reporter.record(OK, "interested_msg", label, f"in #{channel.name}")
                    found = True
                    break
                except (discord.NotFound, discord.Forbidden):
                    continue
        if not found:
            reporter.record(FAIL, "interested_msg", label, f"id={mid} not found in any visible channel")

    # ── forum auto-tags ─────────────────────────────────────────────────────
    for forum_id, tag_id in config.FORUM_CHANNEL_TAG_IDS.items():
        await check_forum_tag(reporter, guild, forum_id, tag_id)

    return reporter.print_summary()


def main():
    intents = discord.Intents.default()
    intents.members = True
    intents.guilds = True
    client = discord.Client(intents=intents)

    exit_code = {"value": 1}  # default to failure

    @client.event
    async def on_ready():
        print(f"connected as @{client.user.name} ({client.user.id})")
        try:
            exit_code["value"] = await run_checks(client)
        finally:
            await client.close()

    try:
        client.run(TOKEN, log_handler=None)
    except KeyboardInterrupt:
        pass
    sys.exit(exit_code["value"])


if __name__ == "__main__":
    asyncio.run(asyncio.sleep(0))  # warm up event loop policy on Windows
    main()
