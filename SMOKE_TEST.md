# Smoke test — post-refactor

Run this after deploying the merged refactor (Phases 0–6) to verify the bot still behaves the way it did. Should take ~15 minutes. The test only covers code paths that **changed** during the refactor or rebase — existing behaviour that was untouched isn't here, because automated tests already cover it.

**No new channels/categories need to be created.** The bot operates against the existing server. A preflight script checks that every channel/role/message ID the bot references is still reachable — run it before you start the bot.

---

## 0. Preflight (30 seconds)

```bash
.venv/Scripts/python scripts/preflight.py
```

Expected: every line begins with `[OK]`. The final summary should read `Summary: <N> pass, 0 fail, 0 skip`.

If any row reports `[FAIL]`, **stop**. Fix the missing/renamed Discord entity (or update the ID in `modules/config/ids.py`) before continuing — the bot will crash partway through `on_ready` otherwise.

---

## 1. Boot + version banner (1 minute)

Start the bot. Watch `mod_chat` (or wherever `general.send()` posts the startup message — see `cogs/core.py::on_ready`).

You should see the message edit through several states in sequence, ending in:

> :green_circle: restart complete!
> ## v5.1.3-2 changelog
> - change literally 2 characters

- [ ] Banner shows **`v5.1.3-2`** (not `v5.1.1-3` — that's the old hardcoded value)
- [ ] Bot status changes to whatever `update_status()` computes (count of available people)
- [ ] No `ERROR` or `WARNING` lines in the bot logs during boot

If on_ready hangs on one of the intermediate states (e.g. stuck at "restoring verification sessions...") that's the same risk as before the refactor — the symptom would point to that subsystem.

---

## 2. `.test` command (10 seconds)

In any channel:

```
.test
```

Expected reply:

> test pass
> -# v5.1.3-2

- [ ] Replies with the new version

---

## 3. Manual Discord kick (the ported audit-log reason behaviour)

Pick a throwaway alt or test account. From the **Discord native UI** (not the `.kick` command — right-click → Kick), kick them with a reason like `smoke test`.

Expected in `mod_chat`:

> :information_source:<:kick:1439803052826689537> @user (DisplayName) got kicked **for smoke test**

- [ ] The message includes ` for smoke test` (the reason suffix)
- [ ] If you kick without a reason, the suffix is absent (i.e. just `got kicked`)

This verifies the kick-reason port from upstream commit `c489373`. The old code didn't show the reason; the new code does.

---

## 4. `.kick` command (the ported DM + invite link)

```
.kick @testaccount smoke test 2
```

Expected:
1. **In a DM to the kicked user:**

   > hey there! you got kicked from **these challenges suck** for the following reason:
   > > smoke test 2
   >
   > this isn't a ban. [you can freely reapply to the server at any point if you wish!](https://discord.gg/AU2yAuXJQ7)

2. **In the chat where you ran the command:**

   > -# sent the kicked guy a dm btw

   (If the user has DMs disabled: `-# couldnt send the guy a dm bc discord dumb asf`. Either is correct — this is the typed-except branch.)

3. **In `mod_chat`** (same as Section 3): `got kicked for smoke test 2`

- [ ] DM arrives with the **`discord.gg/AU2yAuXJQ7`** invite (not the old `JAQvpgzErd` link)
- [ ] Command channel shows the status reply
- [ ] mod_chat shows the audit-log reason

Verifies the kick command port (upstream `04eb889` + `2295a6f` + `954edbd` + `6f2a79f`).

---

## 5. Manual Discord ban

Same flow as Section 3 but Ban from Discord UI with a reason.

Expected in `mod_chat`:

> :information_source:<:ban:1438882547588141118> @user (DisplayName) got banned **for smoke test ban**

- [ ] Reason suffix appears for bans too

---

## 6. `.save` command (the ／ glyph fix)

```
.save SmokeTest @yourself
```

Expected:
- A new category is created named `──／ saves ／──────────` (note the `／` glyph — fullwidth solidus, U+FF0F, **not** the previous `╱` U+2571)
- A `💾┃save-N` channel and a `💾 save N` role are created inside it

- [ ] Open Discord's category list — confirm the slashes look correct
- [ ] Disband afterwards: `.disband` (cleans up the test save)

Verifies the saves-glyph port (upstream `4775ac7`).

---

## 7. Verification thread completion (the AllowedMentions fix)

You'll need a verification thread to test this. Easiest: post your own challenge submission in the verification forum, run through your own verification, complete it as a verifier.

The interesting moment: when the verification is **completed** and the bot edits the original thread post to show the final state (verifiers + role completion).

Expected:
- The final edited message lists verifiers (`<@userid>`) and the role granted (`<@&roleid>`), but **none of those mentions should ping anyone**.

- [ ] No notification badges fire for the mentioned verifiers or for whoever owns the completed challenge

Verifies the `AllowedMentions.none()` change from upstream `430081c` was preserved through the rebase.

---

## 8. Voice channel switching (RoleSession regression check)

This is checking the per-member lock added in Phase 4 didn't break voice-state handling. Easiest stress test:

1. Join `vc`. Should get `in_vc` role.
2. Switch immediately to `vc2`. Should lose `in_vc`, gain `in_vc_2`.
3. Switch immediately to `vc3`. Should lose `in_vc_2`, gain `in_vc_3`.
4. Leave the VC. Should lose `in_vc_3`.

Expected after each switch: your role list reflects only the current VC, no leftovers from previous channels. Watch your member sidebar in Discord — the colour-band should update each time.

- [ ] No "ghost" `in_vc` roles linger after switching
- [ ] If you're a leader, the `in_vc_<n>_leader` role also follows correctly
- [ ] If you have `available`, the `available_not_in_vc_<n>` roles toggle correctly

(The bug fixed in Phase 4 was that two events firing back-to-back would clobber each other. Without the lock, fast switching could leave you with stale roles. With it, the second event waits for the first to commit.)

---

## 9. Quick regression sanity (1 minute)

Things that should still work exactly like before — fast spot-checks:

- [ ] `.points` (yourself) — embed shows your stats
- [ ] `.stats @someone` — embed shows their stats (`.points` alias works too)
- [ ] `.pts @someone` — same (third alias)
- [ ] `.warns @someone` — reports their warn count
- [ ] `.test` — version banner
- [ ] Reply to a mod_chat message that pings someone — bot DMs the original pinger
- [ ] Send `ps` in any channel — bot replies with the private server link
- [ ] Send `bot` in any channel — bot replies `online :white_check_mark:`
- [ ] Add the `⚠️` reaction to the spoiler-roles message — your `spoiler` role gets added
- [ ] Remove the `⚠️` reaction — your `spoiler` role gets removed

---

## 10. Log scan (1 minute)

After the smoke test, scan the bot's log output (or wherever your `systemctl --user` service redirects stdout) for:

```bash
grep -E "(ERROR|CRITICAL|Traceback)" bot.log | tail -40
```

- [ ] No `ERROR` lines (except possibly the deliberate "channel X not available" type if you removed something)
- [ ] No `Traceback` lines

Phase 4 made `general.send()` raise loudly on missing channels — if you see one of those it points at a stale ID in `modules/config/ids.py`.

---

## If something fails

| Symptom | Likely cause |
|---|---|
| Bot crashes on boot | Check preflight output; a referenced ID is gone |
| `.test` shows old version `v5.1.1-3` | The phase-2 porting commit didn't make it to deployed branch; pull `master` again |
| Kick DM doesn't fire | DMs disabled by target (expected `discord.HTTPException` log, NOT a bug) |
| Kick mod_chat msg doesn't include reason | Audit-log entry missing reason OR the 5s heuristic missed; not a refactor regression |
| Verification completion message pings everyone | `AllowedMentions.none()` regression — check `_complete_verification` in `modules/verification.py` |
| Save category uses `╱` not `／` | `modules/saves.py::SAVE_CATEGORY_NAME` wasn't updated — should be `──／ saves ／──────────` |
| Voice role lingers after VC switch | RoleSession lock not engaging — check `_member_locks` defaultdict still exists in `modules/role_management.py` |
| Random tracebacks in log on every gateway message | `on_socket_raw_receive` substring gate broken — should bail on non-`GUILD_JOIN_REQUEST` packets |

Roll back any branch with `git tag` backups still present locally (`backup/pre-rebase-phase-*`, `backup/pre-strip-coauthor-phase-*`).

---

## After all checks pass

```bash
# Clean up the local backup tags
git tag -d $(git tag | grep ^backup/)
```

You're done. The refactor is officially deployed and validated.
