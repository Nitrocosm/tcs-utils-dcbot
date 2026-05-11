import asyncio
import json
import re
from typing import Optional

import aiohttp
import discord
from discord.ext import tasks
from discord.ui import View, Button, Select

from modules import config
from modules.bot_init import bot
from modules.points import parse_challenge_role
from modules.role_management import RoleSession
from modules.badges import badge_emoji_for_name as _badge_emoji

VERIFICATION_FORUM_ID = 1502768684085678200
STATE_FILE = 'verification_state.json'

VERIFIER_ROLE_ID = 1466886852039671962
MOD_ROLE_ID = 1433828741548740781

TAG_UPLOADING = 1502770695359303690
TAG_NEEDS_VERIFICATION = 1502769472715358501
TAG_3_NEEDED = 1502769042317115455
TAG_2_NEEDED = 1502769166728429749
TAG_1_NEEDED = 1502769259238133854
TAG_REPORTED = 1502769374098882671
TAG_VERIFIED = 1502769297498308669

YOUTUBE_RE = re.compile(
    r'(?:https?://)?(?:www\.|m\.)?'
    r'(?:youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/shorts/)'
    r'([a-zA-Z0-9_-]{11})'
)

# ── State ────────────────────────────────────────────────────────────────────

_state: dict[str, dict] = {}

def _load_state() -> dict:
    global _state
    try:
        with open(STATE_FILE, 'r') as f:
            _state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _state = {}
    return _state

def _save_state():
    with open(STATE_FILE, 'w') as f:
        json.dump(_state, f, indent=2, default=str)

def _get_state(thread_id: int) -> dict:
    k = str(thread_id)
    if k not in _state:
        raise KeyError(f"no state for thread {thread_id}")
    return _state[k]

def _init_state(thread_id: int, op_id: int) -> dict:
    k = str(thread_id)
    _state[k] = {
        'thread_id': thread_id,
        'op_id': op_id,
        'message_id': None,
        'state': 'choose_category',
        'selected_category': None,
        'selected_role_id': None,
        'menu_page': 0,
        'video_url': None,
        'verifiers_needed': 0,
        'verifiers_done': 0,
        'verified_by': [],
        'report_resolved': False,
        'ignore': False,
    }
    return _state[k]

def _clean_state(thread_id: int):
    k = str(thread_id)
    _state.pop(k, None)
    _save_state()
    if not any(s.get('state') == 'awaiting_upload' for s in _state.values()):
        if video_polling_loop.is_running():
            video_polling_loop.stop()

# ── Helpers ─────────────────────────────────────────────────────────────────

def _select_emoji_for_challenge(guild: discord.Guild, name: str, points: int) -> Optional[discord.PartialEmoji]:
    emoji = _badge_emoji(guild, name)
    if emoji:
        return emoji
    diff = 0
    if points <= 0:   diff = 0
    elif points <= 2: diff = 1
    elif points <= 4: diff = 2
    elif points <= 7: diff = 3
    elif points <= 10: diff = 4
    elif points <= 13: diff = 5
    elif points <= 17: diff = 6
    elif points <= 23: diff = 7
    else: diff = 8
    placeholders = [
        "<:badge_placeholder_custom_npc:1468336218407436328>",
        "<:badge_placeholder_custom_normal:1468336216171614490>",
        "<:badge_placeholder_custom_hard:1468336226154184867>",
        "<:badge_placeholder_custom_insane:1468336205635784988>",
        "<:badge_placeholder_custom_extreme:1468336223444537414>",
        "<:badge_placeholder_custom_brutal:1468336220609314877>",
        "<:badge_placeholder_custom_maso:1468336214124925073>",
        "<:badge_placeholder_custom_leg:1468336228914172119>",
        "<:badge_placeholder_custom_godlike:1468518569619886111>",
    ]
    m = re.match(r"<:(\w+):(\d+)>", placeholders[diff])
    return discord.PartialEmoji(name=m.group(1), id=int(m.group(2))) if m else None

def _get_challenge_roles(guild: discord.Guild):
    official, custom, joke = [], [], []
    for role in guild.roles:
        info = parse_challenge_role(role)
        if not info:
            continue
        if info['points'] == 0:
            if 'Legacy' in info['name']:
                continue
            joke.append(role)
        elif role.name.startswith('\U0001f3c6'):
            official.append(role)
        elif role.name.startswith('\U0001f4a0'):
            custom.append(role)
    official.sort(key=lambda r: (-(parse_challenge_role(r)['points'] or 0), r.name))
    custom.sort(key=lambda r: (-(parse_challenge_role(r)['points'] or 0), r.name))
    joke.sort(key=lambda r: r.name)
    return official, custom, joke

def _verifiers_for_points(points: int) -> int:
    return 3 if points >= 14 else 2

def _get_youtube_video_id(url: str) -> Optional[str]:
    m = YOUTUBE_RE.search(url)
    return m.group(1) if m else None

async def _check_youtube_video(video_id: str) -> str:
    url = f"https://www.youtube.com/watch?v={video_id}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                text = await resp.text()
                for p in [r'ytInitialPlayerResponse\s*=\s*({.*?});', r'window\["ytInitialPlayerResponse"\]\s*=\s*({.*?});']:
                    m = re.search(p, text, re.DOTALL)
                    if m:
                        try:
                            data = json.loads(m.group(1))
                            break
                        except json.JSONDecodeError:
                            continue
                else:
                    data = None
                if not data:
                    if "Video unavailable" in text or "This video is private" in text:
                        return 'private'
                    return 'available' if resp.status == 200 else 'private'
                playability = data.get('playabilityStatus', {})
                status = playability.get('status', 'ERROR')
                reason = playability.get('reason', '') or playability.get('errorScreen', {}).get('reason', '')
                if status == 'OK':
                    return 'available'
                if 'processing' in reason.lower() or 'upload' in reason.lower():
                    return 'uploading'
                return 'private'
    except Exception:
        return 'private'

async def _set_tags(thread: discord.Thread, tag_ids: list[int]):
    tags = []
    for tid in tag_ids:
        tag = discord.utils.get(thread.parent.available_tags, id=tid)
        if tag:
            tags.append(tag)
    await thread.edit(applied_tags=tags)

def _verifier_tag(count: int) -> int:
    return {3: TAG_3_NEEDED, 2: TAG_2_NEEDED, 1: TAG_1_NEEDED}.get(count, TAG_3_NEEDED)

def _build_challenge_message(state: dict, guild: discord.Guild) -> str:
    role_id = state.get('selected_role_id')
    op_id = state.get('op_id')
    role_mention = f"<@&{role_id}>" if role_id else "???"
    op_mention = f"<@{op_id}>"
    role = guild.get_role(role_id) if role_id else None
    info = parse_challenge_role(role) if role else None
    name = info['name'] if info else "Unknown"
    lines = [f"# {role_mention}", f"{op_mention} completed {name} and awaits verification"]
    if state.get('video_url'):
        lines.append("the video is uploading")
        lines.append(f"-# {state['video_url']}")
    else:
        lines.append("there is no video yet")
    return "\n".join(lines)

def _no_ping():
    return discord.AllowedMentions.none()

# ── Verification logic ──────────────────────────────────────────────────────

_NONCE_SEPARATOR = "::vnonce::"

async def _do_verify(thread: discord.Thread, state: dict, user_id: int, mention: str, bot_msg: discord.Message):
    if user_id not in state['verified_by']:
        state['verified_by'].append(user_id)
    state['verifiers_done'] += 1
    remaining = state['verifiers_needed'] - state['verifiers_done']
    if remaining <= 0:
        await thread.send(f"{mention} marked this as verified - 0 more needed", allowed_mentions=_no_ping())
        await _complete_verification(thread, state, bot_msg)
        return
    _save_state()
    await thread.send(f"{mention} marked this as verified - {remaining} more needed", allowed_mentions=_no_ping())
    await _set_tags(thread, [TAG_NEEDS_VERIFICATION, _verifier_tag(remaining)])
    content = _build_challenge_message(state, thread.guild)
    await bot_msg.edit(content=content, view=VerificationView(remaining))

# ── Flow functions ──────────────────────────────────────────────────────────

async def start_verification_flow(thread: discord.Thread):
    s = _init_state(thread.id, thread.owner_id)
    view = ChallengeCategoryView()
    msg = await thread.send(f"hey <@{thread.owner_id}>! what challenge did you do?", view=view)
    s['message_id'] = msg.id
    _save_state()

async def _handle_video_check(starter_msg: discord.Message, thread: discord.Thread, state: dict, bot_msg: discord.Message):
    video_id = None
    content = starter_msg.content or ''
    video_id = _get_youtube_video_id(content)
    if not video_id and starter_msg.embeds:
        for emb in starter_msg.embeds:
            if emb.url:
                video_id = _get_youtube_video_id(emb.url) or video_id
            if emb.video and emb.video.url:
                video_id = _get_youtube_video_id(emb.video.url) or video_id
    if not video_id:
        await _ask_for_video(thread, state, bot_msg)
        return
    state['video_url'] = content
    _save_state()
    await _process_video(video_id, thread, state, bot_msg)

async def _ask_for_video(thread: discord.Thread, state: dict, bot_msg: discord.Message):
    op_id = state['op_id']
    content = _build_challenge_message(state, thread.guild)
    content += f"\n\n<@{op_id}> please either edit your original post to add a youtube link, or send it here"
    view = NoFootageView()
    await bot_msg.edit(content=content, view=view, allowed_mentions=_no_ping())
    state['state'] = 'awaiting_video'
    _save_state()

async def _process_video(video_id: str, thread: discord.Thread, state: dict, bot_msg: discord.Message):
    status = await _check_youtube_video(video_id)
    if status == 'available':
        state['state'] = 'needs_verification'
        _save_state()
        await _enter_verification_phase(thread, state, bot_msg)
    elif status == 'uploading':
        state['state'] = 'awaiting_upload'
        _save_state()
        await _set_tags(thread, [TAG_UPLOADING])
        content = _build_challenge_message(state, thread.guild)
        await bot_msg.edit(content=content, allowed_mentions=_no_ping())
        if not video_polling_loop.is_running():
            video_polling_loop.start()
    else:
        op_id = state['op_id']
        content = _build_challenge_message(state, thread.guild)
        content += f"\n\n<@{op_id}> that video is private or doesn't exist. please provide a different link, or wait until it's available"
        view = NoFootageView()
        await bot_msg.edit(content=content, view=view, allowed_mentions=_no_ping())

async def _enter_verification_phase(thread: discord.Thread, state: dict, bot_msg: discord.Message):
    needed = state['verifiers_needed']
    state['state'] = 'verification'
    _save_state()
    tag_ids = [TAG_NEEDS_VERIFICATION, _verifier_tag(needed)]
    await _set_tags(thread, tag_ids)
    content = _build_challenge_message(state, thread.guild)
    view = VerificationView(needed)
    await bot_msg.edit(content=content, view=view, allowed_mentions=_no_ping())
    await thread.send(f"<@&{VERIFIER_ROLE_ID}> new challenge to verify")

async def _complete_verification(thread: discord.Thread, state: dict, bot_msg: discord.Message = None):
    state['state'] = 'verified'
    role_id = state['selected_role_id']
    op_id = state['op_id']
    _save_state()
    await _set_tags(thread, [TAG_VERIFIED])
    member = thread.guild.get_member(op_id)
    if member and role_id:
        async with RoleSession(member) as rs:
            rs.add(role_id)
    await thread.send("this run has been verified! :white_check_mark:", allowed_mentions=_no_ping())
    if bot_msg:
        try:
            await bot_msg.edit(content="this run has been verified! :white_check_mark:", view=None, allowed_mentions=_no_ping())
        except:
            pass
    await thread.edit(archived=True, locked=True)
    _clean_state(thread.id)

# ── Message listeners ──────────────────────────────────────────────────────

def _is_verification_thread(channel_id: int) -> bool:
    return str(channel_id) in _state

@bot.listen('on_message')
async def on_verification_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    tid = message.channel.id
    if not _is_verification_thread(tid):
        return
    state = _get_state(tid)
    if state.get('state') not in ('awaiting_video', 'challenge_selected'):
        return
    if message.author.id != state['op_id']:
        return
    video_id = _get_youtube_video_id(message.content)
    if not video_id:
        return
    state['video_url'] = message.content
    _save_state()
    try:
        bot_msg = await message.channel.fetch_message(state['message_id'])
    except:
        return
    await _process_video(video_id, message.channel, state, bot_msg)

@bot.listen('on_message_edit')
async def on_verification_message_edit(before: discord.Message, after: discord.Message):
    if after.author.bot or not after.guild:
        return
    tid = after.channel.id
    if not _is_verification_thread(tid):
        return
    if after.id != tid:
        return
    state = _get_state(tid)
    if state.get('state') not in ('awaiting_video', 'challenge_selected'):
        return
    if after.author.id != state['op_id']:
        return
    video_id = _get_youtube_video_id(after.content)
    if not video_id:
        return
    state['video_url'] = after.content
    _save_state()
    try:
        bot_msg = await after.channel.fetch_message(state['message_id'])
    except:
        return
    await _process_video(video_id, after.channel, state, bot_msg)

# ── Views ────────────────────────────────────────────────────────────────────

class ChallengeCategoryView(View):
    def __init__(self):
        super().__init__(timeout=None)

    async def _is_op(self, interaction: discord.Interaction) -> bool:
        state = _get_state(interaction.channel_id)
        return interaction.user.id == state['op_id']

    async def _handle_category(self, interaction: discord.Interaction, category: str):
        if not await self._is_op(interaction):
            await interaction.response.send_message("this isn't for you", ephemeral=True)
            return
        state = _get_state(interaction.channel_id)
        state['selected_category'] = category
        state['menu_page'] = 0
        state['state'] = 'choose_challenge'
        _save_state()
        official, custom, joke = _get_challenge_roles(interaction.guild)
        roles = {'official': official, 'custom': custom, 'joke': joke}[category]
        view = ChallengeMenuView(category, roles, 0, interaction.guild)
        await interaction.response.edit_message(content="pick a challenge:", view=view)

    @discord.ui.button(label="official challenge", style=discord.ButtonStyle.secondary, custom_id="v:cat:off")
    async def official_btn(self, interaction: discord.Interaction, button: Button):
        await self._handle_category(interaction, 'official')

    @discord.ui.button(label="custom challenge", style=discord.ButtonStyle.secondary, custom_id="v:cat:cust")
    async def custom_btn(self, interaction: discord.Interaction, button: Button):
        await self._handle_category(interaction, 'custom')

    @discord.ui.button(label="joke badge", style=discord.ButtonStyle.secondary, custom_id="v:cat:joke")
    async def joke_btn(self, interaction: discord.Interaction, button: Button):
        await self._handle_category(interaction, 'joke')

    @discord.ui.button(label="this is a failed or incomplete run", style=discord.ButtonStyle.danger, custom_id="v:cat:fail", row=1)
    async def fail_btn(self, interaction: discord.Interaction, button: Button):
        if not await self._is_op(interaction):
            await interaction.response.send_message("this isn't for you", ephemeral=True)
            return
        state = _get_state(interaction.channel_id)
        state['state'] = 'ignore'
        state['ignore'] = True
        _save_state()
        view = ReopenView()
        await interaction.response.edit_message(
            content="ok, i'll ignore this thread then - if you wish to make this thread a verification request again - click the button below",
            view=view,
            allowed_mentions=_no_ping(),
        )


class ReopenView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="make this a verification request", style=discord.ButtonStyle.primary, custom_id="v:reopen")
    async def reopen_btn(self, interaction: discord.Interaction, button: Button):
        state = _get_state(interaction.channel_id)
        if interaction.user.id != state['op_id']:
            await interaction.response.send_message("this isn't for you", ephemeral=True)
            return
        state['state'] = 'choose_category'
        state['ignore'] = False
        _save_state()
        view = ChallengeCategoryView()
        await interaction.response.edit_message(
            content=f"hey <@{state['op_id']}>! what challenge did you do?",
            view=view,
        )


class ChallengeMenuView(View):
    def __init__(self, category: str, roles: list[discord.Role], page: int = 0, guild: discord.Guild = None, per_page: int = 25):
        super().__init__(timeout=None)
        self.category = category
        self.roles = roles
        self.page = page
        self.per_page = per_page
        self.guild = guild

        for cat, label, cid in [
            ('official', 'official challenge', 'v:tab:off'),
            ('custom', 'custom challenge', 'v:tab:cust'),
            ('joke', 'joke badge', 'v:tab:joke'),
        ]:
            disabled = (cat == category)
            btn = Button(label=label, style=discord.ButtonStyle.secondary, disabled=disabled, custom_id=cid, row=0)
            btn.callback = self._make_tab_cb(cat)
            self.add_item(btn)

        start = page * per_page
        page_roles = roles[start:start + per_page]
        options = []
        for role in page_roles:
            info = parse_challenge_role(role)
            if not info:
                continue
            label = (info['name'][:97] + '...') if len(info['name']) > 100 else info['name']
            emoji = _select_emoji_for_challenge(guild, info['name'], info['points']) if guild else None
            options.append(discord.SelectOption(label=label, value=str(role.id), emoji=emoji))
        if not options:
            options.append(discord.SelectOption(label="no challenges available", value="none"))
        select = Select(placeholder="choose a challenge...", options=options, custom_id="v:menu")
        select.callback = self._on_select
        self.add_item(select)

        total_pages = max(1, -(-len(roles) // per_page))
        if total_pages > 1:
            prev_b = Button(label="\u25c0 prev", style=discord.ButtonStyle.secondary, disabled=page == 0, custom_id="v:prev", row=2)
            next_b = Button(label="next \u25b6", style=discord.ButtonStyle.secondary, disabled=page >= total_pages - 1, custom_id="v:next", row=2)
            prev_b.callback = self._make_page_cb(-1)
            next_b.callback = self._make_page_cb(1)
            self.add_item(prev_b)
            self.add_item(next_b)

    def _make_tab_cb(self, category: str):
        async def cb(interaction: discord.Interaction):
            state = _get_state(interaction.channel_id)
            if interaction.user.id != state['op_id']:
                await interaction.response.send_message("this isn't for you", ephemeral=True)
                return
            official, custom, joke = _get_challenge_roles(interaction.guild)
            roles = {'official': official, 'custom': custom, 'joke': joke}[category]
            state['selected_category'] = category
            state['menu_page'] = 0
            _save_state()
            await interaction.response.edit_message(content="pick a challenge:", view=ChallengeMenuView(category, roles, 0, interaction.guild))
        return cb

    def _make_page_cb(self, delta: int):
        async def cb(interaction: discord.Interaction):
            state = _get_state(interaction.channel_id)
            if interaction.user.id != state['op_id']:
                await interaction.response.send_message("this isn't for you", ephemeral=True)
                return
            official, custom, joke = _get_challenge_roles(interaction.guild)
            cat = state.get('selected_category', 'official')
            roles = {'official': official, 'custom': custom, 'joke': joke}[cat]
            new_page = state['menu_page'] + delta
            state['menu_page'] = new_page
            _save_state()
            await interaction.response.edit_message(content="pick a challenge:", view=ChallengeMenuView(cat, roles, new_page, interaction.guild))
        return cb

    async def _on_select(self, interaction: discord.Interaction):
        state = _get_state(interaction.channel_id)
        if interaction.user.id != state['op_id']:
            await interaction.response.send_message("this isn't for you", ephemeral=True)
            return
        val = interaction.data['values'][0]
        if val == 'none':
            await interaction.response.defer()
            return
        role_id = int(val)
        role = interaction.guild.get_role(role_id)
        if not role:
            await interaction.response.send_message("role not found", ephemeral=True)
            return
        info = parse_challenge_role(role)
        if not info:
            await interaction.response.send_message("invalid challenge", ephemeral=True)
            return
        state['selected_role_id'] = role_id
        if not state.get('verifiers_needed'):
            state['verifiers_needed'] = _verifiers_for_points(info['points'])
        state['state'] = 'challenge_selected'
        _save_state()
        content = _build_challenge_message(state, interaction.guild)
        view = ChallengeConfirmView()
        await interaction.response.edit_message(content=content, view=view, allowed_mentions=_no_ping())
        thread = interaction.channel
        if isinstance(thread, discord.Thread):
            try:
                starter = await thread.fetch_message(thread.id)
            except:
                starter = None
            if starter:
                await _handle_video_check(starter, thread, state, interaction.message)


class ChallengeConfirmView(View):
    def __init__(self):
        super().__init__(timeout=None)

        bv = Button(label="verify (X more)", style=discord.ButtonStyle.success, disabled=True, custom_id="v:cfm:vrfy")
        bv.callback = self._dummy
        self.add_item(bv)

        br = Button(label="report", style=discord.ButtonStyle.secondary, disabled=True, custom_id="v:cfm:rpt")
        br.callback = self._dummy
        self.add_item(br)

        bc = Button(label="change challenge", style=discord.ButtonStyle.primary, custom_id="v:cfg:change")
        bc.callback = self._on_change
        self.add_item(bc)

    async def _dummy(self, interaction: discord.Interaction):
        await interaction.response.defer()

    async def _on_change(self, interaction: discord.Interaction):
        state = _get_state(interaction.channel_id)
        if interaction.user.id != state['op_id']:
            await interaction.response.send_message("this isn't for you", ephemeral=True)
            return
        official, custom, joke = _get_challenge_roles(interaction.guild)
        cat = state.get('selected_category', 'official')
        roles = {'official': official, 'custom': custom, 'joke': joke}[cat]
        state['state'] = 'choose_challenge'
        _save_state()
        view = ChallengeMenuView(cat, roles, 0, interaction.guild)
        await interaction.response.edit_message(content="pick a challenge:", view=view)


class NoFootageView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="this challenge doesn't require footage (warn if misused)", style=discord.ButtonStyle.danger, custom_id="v:nofoot")
    async def no_footage_btn(self, interaction: discord.Interaction, button: Button):
        state = _get_state(interaction.channel_id)
        if interaction.user.id != state['op_id']:
            await interaction.response.send_message("this isn't for you", ephemeral=True)
            return
        state['state'] = 'needs_verification'
        _save_state()
        await _enter_verification_phase(interaction.channel, state, interaction.message)


class OwnerVerifyPromptView(View):
    def __init__(self, is_redo: bool):
        super().__init__()
        self.is_redo = is_redo

    @discord.ui.button(label="yes, verify anyway", style=discord.ButtonStyle.primary)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        state = _get_state(interaction.channel_id)
        thread = interaction.channel
        user_id = interaction.user.id
        mention = interaction.user.mention
        try:
            bot_msg = await thread.fetch_message(state['message_id'])
        except:
            await interaction.response.edit_message(content="could not find the verification message", view=None)
            return
        await interaction.response.edit_message(content="proceeding...", view=None)
        await _do_verify(thread, state, user_id, mention, bot_msg)

    @discord.ui.button(label="cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="verification cancelled", view=None)


class VerificationView(View):
    def __init__(self, verifiers_needed: int):
        super().__init__(timeout=None)

        vbtn = Button(label=f"verify ({verifiers_needed} more)", style=discord.ButtonStyle.success, custom_id="v:verify")
        vbtn.callback = self._on_verify
        self.add_item(vbtn)

        rbtn = Button(label="report", style=discord.ButtonStyle.secondary, custom_id="v:report")
        rbtn.callback = self._on_report
        self.add_item(rbtn)

        cbtn = Button(label="change challenge", style=discord.ButtonStyle.primary, custom_id="v:ver:change")
        cbtn.callback = self._on_change
        self.add_item(cbtn)

    async def _is_verifier(self, interaction: discord.Interaction) -> bool:
        member = interaction.user
        if not isinstance(member, discord.Member):
            member = interaction.guild.get_member(member.id)
        if not member:
            return False
        vr = interaction.guild.get_role(VERIFIER_ROLE_ID)
        return bool(vr and vr in member.roles)

    async def _on_verify(self, interaction: discord.Interaction):
        state = _get_state(interaction.channel_id)
        user = interaction.user
        if not isinstance(user, discord.Member):
            user = interaction.guild.get_member(user.id)
        if not user:
            await interaction.response.send_message("could not verify identity", ephemeral=True)
            return

        is_owner = user.id == interaction.guild.owner_id
        has_role = self._is_verifier(interaction)
        already = user.id in state.get('verified_by', [])

        if not is_owner and not has_role:
            await interaction.response.send_message("you don't have permission to do that", ephemeral=True)
            return

        if already:
            if is_owner:
                prompt = OwnerVerifyPromptView(is_redo=True)
                await interaction.response.send_message("you already verified this. are you sure you want to do it again?", view=prompt, ephemeral=True)
            else:
                await interaction.response.send_message("you already verified this", ephemeral=True)
            return

        if is_owner and not has_role:
            prompt = OwnerVerifyPromptView(is_redo=False)
            await interaction.response.send_message("are you sure you want to verify this run?", view=prompt, ephemeral=True)
            return

        thread = interaction.channel
        try:
            bot_msg = await thread.fetch_message(state['message_id'])
        except:
            await interaction.response.send_message("could not find the verification message", ephemeral=True)
            return

        await _do_verify(thread, state, user.id, user.mention, bot_msg)

    async def _on_report(self, interaction: discord.Interaction):
        user = interaction.user
        if not isinstance(user, discord.Member):
            user = interaction.guild.get_member(user.id)
        is_owner = interaction.guild.owner_id == user.id if user else False
        has_role = self._is_verifier(interaction)

        if not is_owner and not has_role:
            await interaction.response.send_message("you don't have permission to do that", ephemeral=True)
            return

        await interaction.response.send_message(
            "are you sure you want to report this verification?",
            view=ReportConfirmView(),
            ephemeral=True,
        )

    async def _on_change(self, interaction: discord.Interaction):
        state = _get_state(interaction.channel_id)
        if interaction.user.id != state['op_id']:
            await interaction.response.send_message("this isn't for you", ephemeral=True)
            return
        official, custom, joke = _get_challenge_roles(interaction.guild)
        cat = state.get('selected_category', 'official')
        roles = {'official': official, 'custom': custom, 'joke': joke}[cat]
        state['state'] = 'choose_challenge'
        _save_state()
        view = ChallengeMenuView(cat, roles, 0, interaction.guild)
        await interaction.response.edit_message(content="pick a challenge:", view=view)


class ReportConfirmView(View):
    def __init__(self):
        super().__init__()

    @discord.ui.button(label="yes, report this", style=discord.ButtonStyle.danger)
    async def confirm_btn(self, interaction: discord.Interaction, button: Button):
        state = _get_state(interaction.channel_id)
        state['state'] = 'reported'
        _save_state()
        thread = interaction.channel
        await _set_tags(thread, [TAG_REPORTED])
        await interaction.response.edit_message(content="this verification has been reported", view=None)
        await thread.send(f"<@&{MOD_ROLE_ID}> this verification has been reported")
        main_msg = thread.get_partial_message(state['message_id'])
        try:
            await main_msg.edit(view=ReportResolveView())
        except:
            pass

    @discord.ui.button(label="cancel", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="report cancelled", view=None)


class ReportResolveView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="resolve report", style=discord.ButtonStyle.primary, custom_id="v:resolve")
    async def resolve_btn(self, interaction: discord.Interaction, button: Button):
        member = interaction.user
        if not isinstance(member, discord.Member):
            member = interaction.guild.get_member(member.id)
        mod_role = interaction.guild.get_role(MOD_ROLE_ID)
        if not mod_role or not member or mod_role not in member.roles:
            if member and member.id != interaction.guild.owner_id:
                await interaction.response.send_message("you don't have permission to do that", ephemeral=True)
                return
        state = _get_state(interaction.channel_id)
        state['state'] = 'verification'
        state['report_resolved'] = True
        _save_state()
        thread = interaction.channel
        remaining = state['verifiers_needed'] - state['verifiers_done']
        await _set_tags(thread, [TAG_NEEDS_VERIFICATION, _verifier_tag(remaining)])
        content = _build_challenge_message(state, interaction.guild)
        view = VerificationView(remaining)
        await interaction.response.edit_message(content=content, view=view, allowed_mentions=_no_ping())
        await thread.send(f"report resolved by {interaction.user.mention}", allowed_mentions=_no_ping())


# ── Polling ─────────────────────────────────────────────────────────────────

@tasks.loop(minutes=15)
async def video_polling_loop():
    for key, s in list(_state.items()):
        if s.get('state') != 'awaiting_upload':
            continue
        video_url = s.get('video_url')
        if not video_url:
            continue
        video_id = _get_youtube_video_id(video_url)
        if not video_id:
            continue
        status = await _check_youtube_video(video_id)
        if status != 'available':
            continue
        thread = bot.get_channel(s['thread_id'])
        if not isinstance(thread, discord.Thread):
            try:
                thread = await bot.fetch_channel(s['thread_id'])
            except:
                continue
            if not isinstance(thread, discord.Thread):
                continue
        try:
            msg = await thread.fetch_message(s['message_id'])
        except:
            continue
        await _enter_verification_phase(thread, s, msg)


# ── Restore ─────────────────────────────────────────────────────────────────

async def restore_sessions(client: discord.Client):
    _load_state()

    # Register persistent views
    client.add_view(ChallengeCategoryView())
    client.add_view(ReopenView())
    client.add_view(ChallengeMenuView('official', [], 0))
    client.add_view(ChallengeConfirmView())
    client.add_view(NoFootageView())
    client.add_view(VerificationView(2))
    client.add_view(ReportResolveView())

    guild = client.get_guild(config.TARGET_GUILD)
    if not guild:
        return

    for key, s in list(_state.items()):
        if s.get('state') in ('verified',):
            _state.pop(key, None)
            _save_state()
            continue
        thread = guild.get_thread(s['thread_id'])
        if not thread:
            thread = client.get_channel(s['thread_id'])
        if not isinstance(thread, discord.Thread):
            try:
                thread = await guild.fetch_channel(s['thread_id'])
            except:
                pass
            if not isinstance(thread, discord.Thread):
                _state.pop(key, None)
                _save_state()
                continue

    if any(s.get('state') == 'awaiting_upload' for s in _state.values()):
        if not video_polling_loop.is_running():
            video_polling_loop.start()

    for s in list(_state.values()):
        if s.get('state') != 'awaiting_upload':
            continue
        video_url = s.get('video_url')
        video_id = _get_youtube_video_id(video_url) if video_url else None
        if not video_id:
            continue
        status = await _check_youtube_video(video_id)
        if status != 'available':
            continue
        thread = guild.get_thread(s['thread_id'])
        if not isinstance(thread, discord.Thread):
            continue
        try:
            bot_msg = await thread.fetch_message(s['message_id'])
        except:
            continue
        await _enter_verification_phase(thread, s, bot_msg)
