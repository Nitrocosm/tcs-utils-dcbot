"""CoreCog — bot lifecycle, error handling, and admin commands.

Owns the `on_ready` orchestrator (single sequence that build cache, restore
state, and prime the bot, in the right order), the periodic `member_checker`
task loop (which depends on the cache being built first), the global
`on_command_error` handler, and the small set of owner/admin commands.
"""
import logging
import subprocess
import sys

import discord
from discord.ext import commands, tasks

from modules import activity, badges, general, role_management, verification

log = logging.getLogger(__name__)

VERSION = 'v6.0.0'

CHANGELOG = f"""
## {VERSION} changelog
- huge refactor: god-file main.py → 8 cogs, modules/ pure logic
- config.py split into a package; module-level IDs centralised
- ruff + pytest + GitHub Actions CI; 156 tests
- .update now runs `pip install -r requirements.txt` before the restart
- countless bug fixes; see REFACTOR.md
"""


class CoreCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def cog_unload(self):
        # Stop the task loop if the cog is unloaded (e.g. during reload).
        if self.member_checker.is_running():
            self.member_checker.cancel()

    # ── periodic checks ─────────────────────────────────────────────────────

    @tasks.loop(minutes=45)
    async def member_checker(self):
        await activity.check_all_members()
        await activity.run_activity_checks()

    @member_checker.error
    async def _member_checker_error(self, error: Exception):
        self.member_checker.stop()
        self.member_checker.start()
        await general.send(
            f'-# :warning: member_checker crashed :/ ```{error}```\n\n'
            '-# restarted it, but if you need to restart it manually use '
            '.force_check_all (available to mods too btw)',
            'mod_chat',
        )
        # the loop will automatically restart on next interval since we don't re-raise

    # ── events ──────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self):
        msg = await general.send(f':radio_button: bot connected... {VERSION}')
        await general.set_status('starting up...', status=discord.Status.idle)  # type: ignore
        await self.bot.wait_until_ready()
        self.bot.add_view(badges.WardrobeOpenView())
        await msg.edit(content=':radio_button: connecting to badge wardrobe...')
        await badges.ensure_wardrobe_message(self.bot)
        await msg.edit(content=':radio_button: syncing host ping reactions...')
        await activity.sync_interested_reactions()
        await msg.edit(content=':radio_button: fetching role relations...')
        await role_management.load_role_relations(self.bot)
        await msg.edit(content=':radio_button: restoring verification sessions...')
        await verification.restore_sessions(self.bot)
        await msg.edit(content=f':green_circle: restart complete!{CHANGELOG}')
        await activity.build_activity_cache()
        if not self.member_checker.is_running():
            self.member_checker.start()

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: Exception):
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

    # ── commands ────────────────────────────────────────────────────────────

    @commands.command()
    @general.try_bot_perms
    @general.has_perms('owner')
    async def load_role_relations(self, ctx):
        await role_management.load_role_relations(self.bot)
        await ctx.message.add_reaction("✅")

    @commands.command()
    @general.try_bot_perms
    @general.has_perms('owner')
    async def p(self, ctx):
        if self.bot.pings:
            await ctx.message.add_reaction("🪫")
            self.bot.pings = False
        else:
            await ctx.message.add_reaction("🔋")
            self.bot.pings = True

    @commands.command()
    @general.try_bot_perms
    @general.has_perms('manage_roles')
    async def force_check_all(self, ctx):
        self.member_checker.stop()
        self.member_checker.start()
        await ctx.message.add_reaction("✅")

    @commands.command()
    @general.try_bot_perms
    async def test(self, ctx):
        await ctx.send(f'test pass\n-# {VERSION}')

    @commands.command()
    @general.try_bot_perms
    @general.has_perms('owner')
    async def force_reactions(self, ctx):
        await activity.sync_interested_reactions()
        await ctx.message.add_reaction("✅")

    @commands.command()
    @general.try_bot_perms
    @general.has_perms('owner')
    async def update(self, ctx):
        await ctx.send(':radio_button: pulling from git...')
        try:
            result = subprocess.run(
                ['git', 'pull'],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return await ctx.send(content=f':warning: git pull failed\n```{result.stderr}```')
            res = result.stdout.splitlines()
            text = ''
            for line in res:
                text = f'{text}\n-# {line}'
            await ctx.send(content=f':radio_button: pulled from git!{text}')

            # Refresh dependencies before restarting. Uses sys.executable so we
            # always hit the same venv the bot is currently running in. pip is
            # fast when everything is already at the pinned version; skipping
            # this can leave the bot in an uninstallable state after a
            # requirements.txt change.
            await ctx.send(content=':radio_button: syncing dependencies...')
            pip_result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt', '--quiet'],
                capture_output=True,
                text=True,
                timeout=180,
            )
            if pip_result.returncode != 0:
                err_tail = pip_result.stderr[-1500:] if pip_result.stderr else '(no stderr)'
                return await ctx.send(
                    content=(
                        ':warning: pip install failed — NOT restarting\n'
                        f'```{err_tail}```'
                    )
                )
            await ctx.send(content=':radio_button: dependencies in sync!')

            await ctx.send(content=':radio_button: restarting bot...')
            subprocess.Popen(['systemctl', 'restart', '--user', 'tcs-utils-dcbot'])

        except subprocess.TimeoutExpired:
            await ctx.send(content=':x: git pull or pip install timed out')
        except Exception as e:
            await ctx.send(content=f':x: error: ```{e}```')


async def setup(bot: commands.Bot):
    await bot.add_cog(CoreCog(bot))
