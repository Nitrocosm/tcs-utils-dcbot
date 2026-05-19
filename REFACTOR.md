# Refactor notes

This document explains what changed during the 2026-05 refactor of `tcs-utils-dcbot`. It's written for the person who owned the codebase *before* the refactor — so you can quickly find where things went, understand the new patterns, and stop second-guessing whether a behaviour change was intentional.

**TL;DR:** the bot still does exactly what it did before, plus a few real bugs were fixed. The 1,769-line `main.py` is now 41 lines and the bot's surface lives in 8 small cogs. Logic stays in `modules/`. Tests + CI now exist.

---

## Table of contents

1. [The new layout at a glance](#the-new-layout-at-a-glance)
2. [Where did my code go? (migration map)](#where-did-my-code-go-migration-map)
3. [New patterns you should know](#new-patterns-you-should-know)
4. [Bugs that got fixed along the way](#bugs-that-got-fixed-along-the-way)
5. [How to do common things now](#how-to-do-common-things-now)
6. [Gotchas](#gotchas)
7. [What was intentionally **not** done](#what-was-intentionally-not-done)
8. [The phase breakdown](#the-phase-breakdown)
9. [Testing & CI](#testing--ci)

---

## The new layout at a glance

```
main.py                     41 lines — sets up logging, loads cog extensions,
                                       calls bot.start(). That's it.

modules/                    PURE LOGIC. No @bot.listen / @tasks.loop at module
                            scope (except verification.py — see Gotchas).
  bot_init.py               builds the bot + intents
  logging_config.py         single stdout handler setup
  config/                   was modules/config.py (380-line monolith)
    settings.py             TOKEN, TARGET_GUILD, check_guild()
    ids.py                  roles{}, channels{}, emoji{}, REACTION_ROLES,
                            FORUM_CHANNEL_TAG_IDS, OWNER_ID
    messages.py             _messages, verification_messages, message()
    __init__.py             re-exports everything — backward-compatible
  general.py                send(), emojify(), permission decorators
  role_management.py        RoleSession (the only sanctioned way to mutate
                            member roles), role-relations cache
  activity.py               VC tracking, inactivity scans, activity cache
  badges.py                 wardrobe view + challenge badge emoji helpers
  moderation.py             mute/warn duration parsing
  points.py                 leaderboard math + challenge-role parsing
  saves.py                  save creation / rename / disband logic
  verification.py           the YouTube-verification state machine + Views
                            (still self-wires its own @bot.listen + tasks.loop)

cogs/                       WIRING. Cogs are thin: they receive Discord events
                            and call into modules/.
  core.py                   on_ready, on_command_error, member_checker loop,
                            admin commands (.test, .p, .force_check_all,
                            .force_reactions, .load_role_relations, .update)
                            Owns VERSION + CHANGELOG.
  moderation.py             14 commands: kick/ban/mute/unmute/warn/warns/
                            clear_warns/lock/unlock/pin/unpin/r/van/war
                            + ConfirmDeleteView
  activity.py               on_voice_state_update, on_raw_reaction_add,
                            on_raw_reaction_remove + .check, .unavailable,
                            .check_inactive_people
  points.py                 .points / .pts / .stats (one impl, three aliases)
                            + ChallengeExpandView
  saves.py                  .save / .rename / .disband
  server_events.py          on_member_join, on_member_remove, on_member_update,
                            on_audit_log_entry_create, on_message,
                            on_socket_raw_receive + join-app handlers
  challenges.py             .create_challenge + 15 helpers + ChallengeVisuals
  verification.py           on_thread_create (forum dispatch + auto-tag)

tests/                      pytest suite. 156 tests, 0 failures.
  test_cogs_load.py         loads every cog offline, asserts listeners /
                            commands / pings flag / polling loop wiring
  test_points.py            parse_challenge_role, calculate_points,
                            leaderboard math
  test_moderation.py        get_timeout_duration, format_timedelta
  test_role_management.py   _parse_relations_from_text, _resolve_to_id
  test_role_hierarchy_cache.py   TTL cache + clear + per-guild isolation
  test_verification.py      YouTube URL parsers, _build_challenge_message,
                            _verifiers_for_points, _next_5min_interval
  test_badges.py            points_to_difficulty + placeholder table
  test_config.py            check_guild, public surface, message()
  test_bot_init.py          intent flags
  test_socket_raw_gate.py   on_socket_raw_receive substring gate
  test_phase4_regressions.py     pins the 3 bugs fixed in Phase 4

.github/workflows/ci.yml    ruff check + pytest on every push/PR
pyproject.toml              ruff + pytest config
.env.example                documents the required TOKEN var
```

---

## Where did my code go? (migration map)

Use this when your muscle-memory grep lands on something that's been moved.

### From `main.py`

| Old location in `main.py` | New location |
|---|---|
| `version`, `changelog` constants | `cogs/core.py` (`VERSION`, `CHANGELOG`) |
| `@tasks.loop member_checker` + error handler | `cogs/core.py::CoreCog.member_checker` |
| `on_ready` | `cogs/core.py::CoreCog.on_ready` |
| `load_role_relations`, `p`, `force_check_all`, `test`, `force_reactions`, `update` commands | `cogs/core.py` |
| `on_command_error` | `cogs/core.py::CoreCog.on_command_error` |
| `van`, `war`, `pin`, `unpin`, `kick`, `ban`, `mute`, `unmute`, `warn`, `warns`, `clear_warns`, `lock`, `unlock`, `r` | `cogs/moderation.py` |
| `ConfirmDeleteView` | `cogs/moderation.py` |
| `on_voice_state_update` | `cogs/activity.py` |
| `on_raw_reaction_add` / `on_raw_reaction_remove` | `cogs/activity.py` (unified — see [Bugs fixed](#bugs-that-got-fixed-along-the-way)) |
| `check`, `check_inactive_people`, `unavailable` commands | `cogs/activity.py` |
| `remove_availability_auto` | `cogs/activity.py` (was the only caller) |
| `points`, `pts`, `stats` commands | `cogs/points.py` (one impl, three aliases) |
| `ChallengeExpandView`, `stat_checker` | `cogs/points.py` |
| `save`, `rename`, `disband` commands | `cogs/saves.py` |
| `on_member_update`, `on_member_join`, `on_member_remove` | `cogs/server_events.py` |
| `on_message` (the easter eggs + RP shortcuts + DM forwarding) | `cogs/server_events.py` |
| `on_audit_log_entry_create` | `cogs/server_events.py` |
| `on_socket_raw_receive` + `_on_join_request_create` / `_on_join_request_delete` | `cogs/server_events.py` |
| `create_challenge` command + 15 helpers (`_visuals_for_points`, `_find_header_role`, `_block_bounds`, `_roles_in_block`, `_custom_divider_and_roles`, `_extract_points`, `_custom_sort_key`, `_emoji_bytes_by_name`, `_apply_visuals_to_role`, `_place_custom_roles`, etc.) + `ChallengeVisuals` | `cogs/challenges.py` |
| `on_thread_create` | `cogs/verification.py` |
| `REACTION_ROLES`, `FORUM_CHANNEL_TAG_IDS` (were module dicts) | `modules/config/ids.py` |
| `OWNER_ID` (hardcoded 4×) | `modules/config/ids.py` |
| `ROLE_ID` (verifier role, also duplicated in verification.py as `VERIFIER_ROLE_ID`) | `modules/config/ids.py` as `roles['verifier']` |
| Bare literal `1426972810332340406` (challenge log thread) | `modules/config/ids.py` as `channels['challenge_log_thread']` |

### From `modules/config.py`

The old monolithic file is now a package:

| What you want | Where to find it |
|---|---|
| `TOKEN`, `TARGET_GUILD`, `check_guild()` | `modules/config/settings.py` |
| `roles`, `channels`, `emoji` dicts; `OWNER_ID`; `REACTION_ROLES`; `FORUM_CHANNEL_TAG_IDS` | `modules/config/ids.py` |
| `_messages`, `verification_messages`, `message()` | `modules/config/messages.py` |

**Imports keep working.** `from modules.config import roles, message, TOKEN` still works — `__init__.py` re-exports the whole public surface. If you wrote `config.roles['mod']`, that still works too.

### Modules that didn't move

`activity.py`, `badges.py`, `general.py`, `moderation.py`, `points.py`, `role_management.py`, `saves.py`, `verification.py` are all in the same place. They got small additions (typed except clauses, logging, a couple of new helpers) but the public API didn't change.

---

## New patterns you should know

### 1. `RoleSession` is now mandatory for role edits

Never call `member.add_roles()` / `member.remove_roles()` / `member.edit(roles=...)` directly. Always use `RoleSession`:

```python
from modules.role_management import RoleSession

async with RoleSession(member) as rs:
    rs.add('available')           # by string key from config.roles
    rs.add(some_role_id)          # by int
    rs.add(some_role_obj)         # by discord.Role
    rs.remove('inactive')
# auto-commits on context exit
```

What it does on commit:
- Acquires a **per-member asyncio.Lock** so concurrent contexts don't clobber each other
- Refetches the member fresh from the guild cache (avoids stale role lists)
- Applies role relations (parent → child role expansion) from the `_role_relations` cache
- Applies "ensure" rules (e.g. `available_leader` follows from `available` + `leader`)
- Applies category rules (category role on/off, `🚫 none` markers)
- Filters out bot-specific roles
- Diffs against current state, only calls `member.edit()` if something actually changed

If you need to skip auto-commit (you want to do something after the role list is computed but before the API call), use `RoleSession(member, autocommit=False)` and call `await rs.commit()` manually.

### 2. Commands live in cogs, logic lives in modules

```python
# cogs/saves.py — wiring
@commands.command()
async def rename(self, ctx, *args):
    name = " ".join(args) if args else None
    await rename_save(ctx, name)        # <-- delegates

# modules/saves.py — logic
async def rename_save(ctx, name):
    # ...the actual work...
```

The cog method should be thin. Argument parsing, Discord-specific glue, decorators. The module function does the real work and is testable in isolation.

### 3. Centralised logging

```python
import logging
log = logging.getLogger(__name__)

log.info("did the thing")
log.warning("the thing was a bit off: %s", reason)
log.error("the thing broke: %s", exc, exc_info=True)
log.exception("the thing broke")    # equivalent to log.error(..., exc_info=True)
```

No `print()` calls. The setup in `modules/logging_config.py` installs a single stdout handler with format `%(asctime)s %(levelname)-8s %(name)s: %(message)s`.

### 4. Typed exceptions, not bare `except:`

```python
# DON'T
try:
    await something()
except:
    pass

# DO
try:
    await something()
except discord.Forbidden:
    log.warning("missing perms for X", exc_info=True)
except discord.HTTPException:
    log.warning("X failed, will retry", exc_info=True)
```

The 15 bare-except clauses that existed before are all gone. Bare except swallows `KeyboardInterrupt`, `SystemExit`, and silent bugs.

### 5. Config access patterns

```python
from modules import config

config.TOKEN                          # env-derived
config.OWNER_ID
config.TARGET_GUILD
config.check_guild(guild.id)
config.roles['mod']
config.channels['mod_chat']
config.emoji['star_completion']
config.REACTION_ROLES
config.FORUM_CHANNEL_TAG_IDS
config.message('kick', mention=member.mention)   # picks random template + formats
```

All of these existed before the refactor. The only thing that changed is the file they live in (now split across `settings.py` / `ids.py` / `messages.py`).

---

## Bugs that got fixed along the way

These are real bugs that existed in the pre-refactor code. Each one is now covered by a regression test in `tests/test_phase4_regressions.py` or its area-specific test file.

### Role-clobbering race condition (`role_management.py`)

**Symptom:** member's roles would occasionally be partially wiped — e.g. their `in_vc` role + their `available_not_in_vc` role both end up set, or a freshly-added challenge role disappears.

**Cause:** `on_voice_state_update` and `on_member_update` could both fire for the same member within milliseconds. Each opened its own `RoleSession`, read the member's current roles, computed a final list, and called `member.edit(roles=...)`. Last-writer-wins meant the second `edit` blew away changes the first one made.

**Fix:** `RoleSession.commit()` now acquires a per-member `asyncio.Lock`. Different members can still commit concurrently; the same member is serialised. Inside the lock we refetch the member's roles fresh from the guild cache before computing the diff. See `modules/role_management.py` lines ~15 + `commit()` body.

### `general.send()` silently failed on missing channels

**Symptom:** announcements to `mod_chat` or `chat` channels would occasionally just not happen, with no log entry, when the bot was reconnecting or the channel had been re-created.

**Cause:** `general.send()` did `bot.get_channel(...).send(...)` — if `get_channel` returned `None`, the `.send` raised AttributeError into the asyncio event loop, where it became a warning nobody saw.

**Fix:** explicit `if channel is None: log.error(...); raise RuntimeError(...)` so the failure is loud. See `modules/general.py::send`.

### `on_member_remove` reverse-VC race with audit log

(Not actually fixed — flagged as latent risk.) The audit-log `< 5s` heuristic in `cogs/server_events.py::on_member_remove` is inherently fragile because Discord can delay audit log writes. If you see "left the server" announcements for users who were actually kicked/banned, this is why. Not changed in the refactor; documented here.

### 15 bare `except:` clauses

Replaced with typed exceptions + logging across `modules/general.py`, `modules/verification.py`, `modules/role_management.py`, `cogs/server_events.py`, etc. The kick-DM block in `cogs/moderation.py` uses `except discord.HTTPException` rather than bare `except:`.

### Gateway packet over-parsing

**Symptom:** none user-visible, but `on_socket_raw_receive` was running `json.loads()` on every WebSocket packet (hundreds per minute in a busy guild) just to throw 99.9% of them away.

**Fix:** cheap substring gate `if "GUILD_JOIN_REQUEST" not in msg: return` before `json.loads`. See `cogs/server_events.py::on_socket_raw_receive`.

### `_get_role_hierarchy` re-computed every commit

**Symptom:** every `RoleSession.commit()` re-sorted and re-walked all guild roles to detect category roles.

**Fix:** 30s TTL cache per guild. `load_role_relations` flushes the cache when the admin re-runs it. See `modules/role_management.py::_get_role_hierarchy` + `clear_hierarchy_cache`.

### Unused `presences` intent

**Symptom:** none, but Discord was sending us PRESENCE_UPDATE for every member's activity change. We never read it.

**Fix:** dropped from `modules/bot_init.py`. Reduces gateway traffic + privileged-intent surface in the Dev Portal.

### Behaviour deduplications

These weren't bugs but were duplicated logic that quietly drifted:
- `on_raw_reaction_add` and `on_raw_reaction_remove` were ~90% identical. Unified into one handler that takes an `added: bool` parameter (`cogs/activity.py`).
- `_check_mod` was inlined into 3 verification Views. Lifted to a module-level helper.
- `send_timed_delete_msg` reimplemented `timed_delete_msg`'s logic. Now delegates.
- `points` / `pts` / `stats` were three identical commands. Now one method with `aliases=['pts', 'stats']`.
- `_messages['difficulty_X']` placeholders were inlined; `points_to_difficulty()` had a hardcoded ladder. Lifted to a shared `DIFFICULTY_PLACEHOLDERS` list.
- Two role keys (`completion_server_star_star`, `completion_server_base_star`) held the same IDs as `completion_all_ultimate` / `completion_all_base` and were never referenced. Removed.

---

## How to do common things now

### Adding a new command

1. Pick the cog whose theme matches your command. Most things fit into one of the existing 8.
2. Add a method to the cog class:

```python
# cogs/moderation.py
@commands.command()
@general.try_bot_perms
@general.has_perms('moderate_members')
async def my_new_command(self, ctx, member: discord.Member, *, reason: str = None):
    # ...
```

3. If the command does non-trivial work, put the work in a `modules/` file and have the cog method just call it.
4. Add the command name to `EXPECTED_COMMANDS` in `tests/test_cogs_load.py` so the loader test asserts it exists.

### Adding a new event handler

1. Pick the cog whose theme matches. If it's a server-state event (member join/leave/edit, audit log), `cogs/server_events.py`. If it's a voice or reaction event, `cogs/activity.py`. Otherwise probably `cogs/core.py`.
2. Add the handler:

```python
@commands.Cog.listener()
async def on_typing(self, channel, user, when):
    # ...
```

Note `@commands.Cog.listener()` (additive — multiple cogs can listen for the same event) rather than `@bot.event` (which would override discord.py's default).

3. Add the event name to `EXPECTED_LISTENERS` in `tests/test_cogs_load.py`.

### Adding a brand new cog

Rare, but: create `cogs/<name>.py`, write a class with `setup(bot)` at the bottom, append `'cogs.<name>'` to the `EXTENSIONS` list in `main.py`. The `test_cogs_load.py` `EXPECTED_COGS` set needs updating too.

### Adding a test

Drop a `test_*.py` file in `tests/`. CI runs `pytest tests/ -v` on every push and PR. Cog tests have a pattern in `test_cogs_load.py` (a module-scoped fixture that loads all extensions inside one `async with bot:` block and snapshots the state).

Pure-logic tests are much easier than wiring tests. Most of the test suite is pure-logic: parse this string, compute these points, format this duration. Aim for that.

### Adding a config entry

| Type | Goes in | How to use it |
|---|---|---|
| Role ID | `modules/config/ids.py` `roles{}` | `config.roles['my_key']` |
| Channel/thread ID | `modules/config/ids.py` `channels{}` | `config.channels['my_key']` |
| Emoji ID/string | `modules/config/ids.py` `emoji{}` | `config.emoji['my_key']` |
| User-facing message | `modules/config/messages.py` `_messages{}` | `config.message('my_key', name=member.mention)` |
| Verification flow message | `modules/config/messages.py` `verification_messages{}` | `config.verification_messages['my_key']` (or `VM['my_key']` inside verification.py) |
| Env var | `modules/config/settings.py` | direct attribute, e.g. `config.MY_VAR` |

### Changing the version/changelog shown on bot startup

`cogs/core.py` top — `VERSION` and `CHANGELOG` constants. They appear in `on_ready`'s green-circle message and in `.test`'s reply.

### Running tests + lint locally

```
pip install -r requirements.txt
pip install ruff pytest
ruff check .
pytest tests/ -v
```

Or just push — CI will tell you.

---

## Gotchas

### 1. The `# noqa` import in `main.py` is load-bearing

```python
import modules.verification  # noqa: F401 -- side-effect: registers @bot.listen / @tasks.loop
```

This line looks unused. It's not — importing `modules/verification.py` triggers three module-scope decorators that wire `on_message`, `on_message_edit`, and a 5-minute polling loop onto the bot. **If a linter or refactor removes this line, verification stops working silently** (no error, no missing-channel warning — just nothing happens when someone posts to a verification thread).

Phase 2.5 (deferred) would migrate that wiring into `cogs/verification.py` so this import becomes unnecessary. Until then, keep the line.

### 2. `bot.pings` is in-memory only

The `.p` command (toggle pings) flips a `bot.pings` attribute. It's initialised to `True` in `main.py` on every restart. We didn't persist it because it's low-value for a hobby bot — if you mark yourself temporarily unavailable and restart the bot, you're now ping-able again. Living with this is fine; persisting it is a 10-line addition if you ever want it.

### 3. `on_message` runs in two places

`cogs/server_events.py::on_message` (easter eggs, RP shortcuts, DM forwarding) is a `@commands.Cog.listener()` — it's *additive*. discord.py's default `on_message` still runs after it and dispatches commands. **Do not** add `await self.bot.process_commands(message)` to the cog handler or every command will fire twice.

`modules/verification.py::on_message_for_verification` is also additive (it's a `@bot.listen('on_message')`). All three coexist cleanly.

### 4. Cogs that are unloaded leak module-level listeners

Standard discord.py behaviour: `bot.unload_extension('cogs.X')` removes the cog and its listeners. But `modules/verification.py`'s `@bot.listen` decorators run at module-import time and aren't bound to any cog — they stay attached forever. If you reload `modules.verification`, you'll register a *second* copy. (Phase 2.5 fixes this too.)

### 5. The audit-log heuristic in `on_member_remove`

`(discord.utils.utcnow() - entry.created_at).total_seconds() < 5` — Discord's audit log can be delayed by more than 5 seconds, in which case a kicked user shows up as "left the server" instead. This is unchanged from the pre-refactor code. If you want to fix it, the right solution is to track kick/ban actions in-memory when *we* execute them and consult that map first.

### 6. `RoleSession` resolves string keys via `config.roles`

`rs.add('available')` works because `_resolve_to_id` does `config.roles.get('available')`. If you pass a string that isn't in `config.roles`, the add is silently dropped (no exception, just nothing happens). Discord-side validation can't catch this. Be deliberate about string vs. int vs. `discord.Role` inputs.

### 7. `RoleSession` only knows about the guild it was constructed for

If you somehow pass it a `member` from a different guild, the role lookups will be wrong. The bot only operates in `TARGET_GUILD`, so this shouldn't happen in practice — but `check_guild()` is the gate that protects this and it must run before any RoleSession is opened.

### 8. The hierarchy cache has a 30s TTL

If you create/rename/move category roles (the `──╱ ... ─` ones or `🚫 none`), the cache is stale for up to 30s. Either wait, or call `clear_hierarchy_cache()` from `modules.role_management`, or run `.load_role_relations` which flushes it. Normal challenge role creates don't affect the cache (those aren't category roles).

---

## What was intentionally **not** done

- **Phase 2.5** — moving `modules/verification.py`'s three module-scope decorators (`@bot.listen('on_message')`, `@bot.listen('on_message_edit')`, `@tasks.loop video_polling_loop`) into `cogs/verification.py`. Deferred because verification is the most complex module and the wiring carries silent-failure risk without behaviour tests. Phase 5's pure-logic tests on the verification helpers make this safer now, but it wasn't worth the extra session time.
- **`bot.pings` persistence** — low value for a hobby bot. See Gotcha 2.
- **Activity cache persistence** — same reasoning. The cache rebuilds on `on_ready` (5–10s).
- **Audit-log race fix in `on_member_remove`** — see Gotcha 5. Needs in-memory action tracking, which is a real chunk of work.
- **Stricter ruff rules** — the baseline is `E`, `F`, `W` only. Stricter rule sets (B, UP, SIM, etc.) would drown a single PR in suggestions. Add them per-area when you feel like it.
- **Reformatting the codebase with `ruff format`** — not done. Diffs would be enormous and pure noise. If you want it, run it as a single isolated commit you can ignore in blame.
- **Touching the giant comment-heavy easter egg in `on_message`** (the `'ps'` reply, `'npc' == content.lower()`, `'bot' == content.lower()`, `'one more'`, the lostya-ping reminder, RP actions). Left exactly as-is.
- **Reworking the verification YouTube-polling cadence** — `@tasks.loop(minutes=5)` is what it was. If YouTube rate-limits become an issue, that's where to look.

---

## The phase breakdown

Each phase was one PR / branch. They stack linearly off `master`. All branches are pushed to `origin`.

| Phase | Branch | Theme | Behaviour change? |
|---|---|---|---|
| 0 + 1 | `refactor/phase-0-1-tooling-config` | tooling baseline + config package split + logging | none |
| 2 | `refactor/phase-2-cogs` | extract `main.py` into 8 cogs; permission decorators position-agnostic; one porting commit absorbs upstream's kick-DM/changelog changes | none (porting preserves them) |
| 3 | `refactor/phase-3-dedup` | unify reaction handlers, `_check_mod`, `send_timed_delete_msg`, points/pts/stats, difficulty placeholders | none |
| 4 | `refactor/phase-4-correctness` | `general.send` raises on missing channel; RoleSession per-member lock; 15 bare excepts → typed + logged | **yes**: bugs fixed |
| 5 | `refactor/phase-5-tests` | 156 pytest tests; CI workflow; ruff baseline → 0 | none |
| 6 | `refactor/phase-6-polish` | drop presences intent; gate `on_socket_raw_receive`; cache role hierarchy | **yes**: perf wins, no semantic change |

The "porting commit" in Phase 2 (`chore: port post-branch master commits into new cog structure`) deserves a sentence: while the refactor was in progress, upstream master picked up 8 commits that all touched `main.py` (kick auto-DM, kick/ban reasons in mod_chat, version bumps, verification AllowedMentions, saves category glyph). Since `main.py` got deleted in Phase 2, those changes were re-applied to the new cog locations in one commit at the tip of phase-2.

---

## Testing & CI

```
.github/workflows/ci.yml    runs on every push + pull_request to any branch
  - ruff check .            (must report 0)
  - pytest tests/ -v        (must report 156 passed)
```

Locally:
```
pip install ruff pytest
ruff check .
pytest tests/ -v
```

The test suite is fast (~1 second) and pure-Python — no Discord connection needed. Most tests run pure logic against synthetic inputs. `test_cogs_load.py` loads the bot offline (no token check, no network) to verify wiring.

**Don't merge anything that takes ruff above 0 or breaks a test.** The CI will catch it but PR reviews are faster if you check locally first.

---

## Quick-reference: file → owner

| Need to change... | Touch this file |
|---|---|
| The boot sequence (load extensions, set up logging) | `main.py` |
| The bot's Discord intents | `modules/bot_init.py` |
| Logging format / level | `modules/logging_config.py` |
| A role/channel/emoji ID | `modules/config/ids.py` |
| A user-facing message template | `modules/config/messages.py` |
| Environment variable handling | `modules/config/settings.py` |
| How role mutations are applied | `modules/role_management.py` |
| The version banner on startup | `cogs/core.py` (top) |
| The 45-min member-checker cadence | `cogs/core.py::CoreCog.member_checker` |
| A moderation command | `cogs/moderation.py` |
| Voice channel tracking / reaction roles | `cogs/activity.py` |
| The points / leaderboard display | `cogs/points.py` |
| Server save logic | `cogs/saves.py` |
| Member join / leave / kick / ban announcements | `cogs/server_events.py` |
| Easter eggs, RP shortcuts, DM forwarding | `cogs/server_events.py::on_message` |
| Voice channel status edit handling | `cogs/server_events.py::on_audit_log_entry_create` |
| The `.create_challenge` command | `cogs/challenges.py` |
| Verification thread dispatch + forum auto-tag | `cogs/verification.py` |
| The verification state machine itself | `modules/verification.py` |
| YouTube link parsing | `modules/verification.py` |
| Challenge badge emoji lookup / wardrobe | `modules/badges.py` |
| Save creation logic (not the command) | `modules/saves.py` |
| Mute duration parsing | `modules/moderation.py` |
| Points / leaderboard math | `modules/points.py` |
| `general.send`, `emojify`, permission decorators | `modules/general.py` |
