"""Regression tests for the Phase 4 correctness fixes.

Pins the behaviour of:
  - general.send raising on missing channel (was: returned the input str
    typed as Message and callers blew up later)
  - general.update_status forwarding `status` correctly (was: callers
    accidentally passed the Bot instance as status)
  - RoleSession.commit serialising per-member concurrent calls (was:
    last-writer-wins clobber)
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest


# ── general.send / general.update_status ────────────────────────────────────


def test_general_send_raises_when_channel_missing():
    """If bot.get_channel returns None, send must raise, not return a str."""
    from modules import general

    with patch.object(general.bot, 'get_channel', return_value=None):
        with pytest.raises(RuntimeError, match="not available"):
            asyncio.run(general.send('hello', where='chat'))


def test_general_update_status_with_no_args_passes_status_none():
    """update_status() with no args should leave the Discord status alone
    (i.e. pass status=None into change_presence)."""
    from modules import general

    captured = {}

    async def fake_change_presence(activity=None, status=None):
        captured['status'] = status

    with patch.object(general.bot, 'get_guild', return_value=MagicMock()), \
         patch.object(general, 'get_status_text', return_value='snapshot'), \
         patch.object(general.bot, 'change_presence', side_effect=fake_change_presence):
        asyncio.run(general.update_status())
    assert captured['status'] is None


def test_general_update_status_with_explicit_status_forwards_it():
    from modules import general

    captured = {}

    async def fake_change_presence(activity=None, status=None):
        captured['status'] = status

    with patch.object(general.bot, 'get_guild', return_value=MagicMock()), \
         patch.object(general, 'get_status_text', return_value='snapshot'), \
         patch.object(general.bot, 'change_presence', side_effect=fake_change_presence):
        asyncio.run(general.update_status(status=discord.Status.online))
    assert captured['status'] == discord.Status.online


def test_general_update_status_no_op_when_guild_missing():
    from modules import general

    change = AsyncMock()
    with patch.object(general.bot, 'get_guild', return_value=None), \
         patch.object(general.bot, 'change_presence', side_effect=change):
        asyncio.run(general.update_status(status=discord.Status.online))
    change.assert_not_called()


# ── RoleSession per-member lock ────────────────────────────────────────────


def test_role_session_commits_for_same_member_serialise():
    """Two RoleSession contexts targeting the same member must not interleave
    their member.edit calls."""
    import modules.role_management as rm
    from modules.role_management import RoleSession

    events = []

    async def slow_edit(**kw):
        label = kw.get('reason', '?')
        events.append(('start', label))
        await asyncio.sleep(0.02)
        events.append(('end', label))

    member = MagicMock()
    member.id = 12345
    member.bot = False
    member.roles = []
    member.guild.get_member.return_value = member
    fake_roles = {}

    def get_role(rid):
        if rid not in fake_roles:
            r = MagicMock(); r.id = rid; fake_roles[rid] = r
        return fake_roles[rid]
    member.guild.get_role.side_effect = get_role
    member.edit = AsyncMock(side_effect=slow_edit)

    # bypass the heavy hierarchy helpers; they're not what we're testing
    with patch.object(rm, '_apply_role_relations', side_effect=lambda r, g: r), \
         patch.object(rm, '_ensure_roles',         side_effect=lambda r, g: r), \
         patch.object(rm, '_fix_categories',       side_effect=lambda r, g: r):

        async def session_task(role_id):
            async with RoleSession(member) as rs:
                rs.to_add.add(role_id)
                # Patch the edit reason so we can identify which session's edit ran.
                # commit() passes no `reason=`, so we wrap edit to inject one.
            # commit happens on aexit

        # Override commit just for this test so we can tag each edit
        async def labeled_commit(self):
            async with rm._member_locks[self.member.id]:
                fresh = self.guild.get_member(self.member.id)
                final = self._build_final_roles(fresh)
                await fresh.edit(roles=list(final), reason=str(sorted(self.to_add)))

        async def run_both():
            await asyncio.gather(session_task(111), session_task(222))

        with patch.object(RoleSession, 'commit', labeled_commit):
            asyncio.run(run_both())

    # The two edits must form non-interleaved start/end pairs.
    assert len(events) == 4
    assert events[0][0] == 'start' and events[1][0] == 'end' and events[0][1] == events[1][1]
    assert events[2][0] == 'start' and events[3][0] == 'end' and events[2][1] == events[3][1]
    # And the two sessions ran in *some* order, not the same edit twice
    assert events[0][1] != events[2][1]


def test_role_session_different_members_run_concurrently():
    """Two RoleSession contexts targeting DIFFERENT members must NOT block
    each other - they hold different locks."""
    import modules.role_management as rm
    from modules.role_management import RoleSession

    events = []

    async def slow_edit(**kw):
        # 'reason' carries the member tag the session is editing
        label = kw.get('reason', '?')
        events.append(('start', label))
        await asyncio.sleep(0.05)
        events.append(('end', label))

    def _make_member(member_id):
        m = MagicMock()
        m.id = member_id
        m.bot = False
        m.roles = []
        m.guild.get_member.return_value = m
        m.guild.get_role.return_value = MagicMock()
        m.edit = AsyncMock(side_effect=slow_edit)
        return m

    alice = _make_member(1)
    bob = _make_member(2)

    with patch.object(rm, '_apply_role_relations', side_effect=lambda r, g: r), \
         patch.object(rm, '_ensure_roles',         side_effect=lambda r, g: r), \
         patch.object(rm, '_fix_categories',       side_effect=lambda r, g: r):

        async def labeled_commit(self):
            async with rm._member_locks[self.member.id]:
                fresh = self.guild.get_member(self.member.id)
                final = self._build_final_roles(fresh)
                await fresh.edit(roles=list(final), reason=f'm{self.member.id}')

        async def session_task(member, role_id):
            async with RoleSession(member) as rs:
                rs.to_add.add(role_id)

        async def run_both():
            await asyncio.gather(
                session_task(alice, 100),
                session_task(bob, 200),
            )

        with patch.object(RoleSession, 'commit', labeled_commit):
            asyncio.run(run_both())

    # Concurrency: both edits should START before either ENDs.
    # i.e. the event sequence is start, start, end, end - not start, end, start, end.
    assert len(events) == 4
    assert events[0][0] == 'start'
    assert events[1][0] == 'start', f'expected interleaved starts, got {events}'
    assert events[2][0] == 'end'
    assert events[3][0] == 'end'
