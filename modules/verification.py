import json
import logging
import re
import time
from typing import Optional

import aiohttp
import discord
from discord import AllowedMentions
from discord.ext import tasks
from discord.ui import View, Button, Select

from modules import config
from modules.bot_init import bot
from modules.points import parse_challenge_role
from modules.role_management import RoleSession
from modules.badges import DIFFICULTY_PLACEHOLDERS, badge_emoji_for_name as _badge_emoji, points_to_difficulty

log = logging.getLogger(__name__)

VM = config.verification_messages

VERIFICATION_FORUM_ID = config.VERIFICATION_FORUM_ID
STATE_FILE = 'verification_state.json'

VERIFIER_ROLE_ID = config.roles['verifier']
MOD_ROLE_ID = config.roles['mod']

TAG_UPLOADING = 1502770695359303690
TAG_NEEDS_VERIFICATION = 1502769472715358501
TAG_3_NEEDED = 1502769042317115455
TAG_2_NEEDED = 1502769166728429749
TAG_1_NEEDED = 1502769259238133854
TAG_REPORTED = 1502769374098882671
TAG_VERIFIED = 1502769297498308669
TAG_REJECTED = 1503659032890839150
TAG_MANUAL = 1503867427958816929
TAG_PREPARING = 1503895658678059141

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
        'video_ready': False,
        'verifiers_needed': 0,
        'verifiers_done': 0,
        'verified_by': [],
        'last_verifier': None,
        'next_check_at': None,
        'report_resolved': False,
        'ignore': False,
        'no_footage': False,
        'rejected': False,
        'verifier_pinged': False,
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
    placeholder = DIFFICULTY_PLACEHOLDERS[points_to_difficulty(points)]
    m = re.match(r"<:(\w+):(\d+)>", placeholder)
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

def _get_youtube_url(text: str) -> Optional[str]:
    m = YOUTUBE_RE.search(text)
    return m.group(0) if m else None

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
                        return 'uploading'
                    return 'available' if resp.status == 200 else 'uploading'
                playability = data.get('playabilityStatus', {})
                status = playability.get('status', 'ERROR')
                if status == 'OK':
                    return 'available'
                return 'uploading'
    except Exception as e:
        log.debug('youtube check failed: %s', e)
        return 'uploading'

async def _set_tags(thread: discord.Thread, tag_ids: list[int]):
    tags = []
    for tid in tag_ids:
        tag = discord.utils.get(thread.parent.available_tags, id=tid)
        if tag:
            tags.append(tag)
    await thread.edit(applied_tags=tags)

def _verifier_tag(count: int) -> int:
    return {3: TAG_3_NEEDED, 2: TAG_2_NEEDED, 1: TAG_1_NEEDED}.get(count, TAG_3_NEEDED)

def _next_5min_interval() -> int:
    now = int(time.time())
    return ((now // 300) + 1) * 300

def _build_challenge_message(state: dict, guild: discord.Guild) -> str:
    VM = config.verification_messages
    role_id = state.get('selected_role_id')
    op_id = state.get('op_id')
    role = guild.get_role(role_id) if role_id else None
    info = parse_challenge_role(role) if role else None
    name = info['name'] if info else "???"
    role_mention = f"<@&{role_id}>" if role_id else "???"
    op_mention = f"<@{op_id}>"
    st = state.get('state', '')

    lines = [
        VM["msg_header_title"].format(role_mention=role_mention),
        VM["msg_header_body"].format(op_mention=op_mention, name=name),
    ]

    video_url = state.get('video_url')
    needed = state.get('verifiers_needed', 0)
    done = state.get('verifiers_done', 0)

    if st == 'rejected':
        lines.append(VM["msg_body_rejected"])
    elif st == 'reported':
        lines.append(VM["msg_body_reported"])
    elif st == 'manual':
        lines.append(VM["msg_body_manual"])
    elif video_url and state.get('video_ready'):
        lines.append(VM["msg_body_ready"].format(done=done, needed=needed))
        last = state.get('last_verifier')
        if last:
            lines.append(VM["msg_body_ready_last"].format(last=last))
    elif video_url:
        lines.append(VM["msg_body_uploading"])
        nxt = state.get('next_check_at')
        if nxt:
            lines.append(VM["msg_body_uploading_check"].format(ts=nxt))
        lines.append(VM["msg_body_uploading_hint"])
    elif state.get('no_footage'):
        lines.append(VM["msg_body_no_footage"])
    else:
        lines.append(VM["msg_body_no_video"])
        if st == 'awaiting_video':
            lines.append(VM["msg_body_no_video_hint"])

    if video_url:
        lines.append(VM["msg_url_line"].format(url=video_url))

    return "\n".join(lines)

def _no_ping():
    return discord.AllowedMentions.none()


async def _check_mod(interaction: discord.Interaction) -> bool:
    """Return True if the interaction's invoker is a mod (or the server owner).

    On failure, sends the `err_not_verifier` ephemeral response so callers
    can just `if not await _check_mod(interaction): return`.
    """
    member = interaction.user
    if not isinstance(member, discord.Member):
        member = interaction.guild.get_member(member.id)
    mod_role = interaction.guild.get_role(MOD_ROLE_ID)
    if not mod_role or not member or mod_role not in member.roles:
        if not member or member.id != interaction.guild.owner_id:
            await interaction.response.send_message(VM["err_not_verifier"], ephemeral=True)
            return False
    return True


# ── Verification logic ──────────────────────────────────────────────────────

_NONCE_SEPARATOR = "::vnonce::"

async def _do_verify(thread: discord.Thread, state: dict, user_id: int, mention: str, bot_msg: discord.Message):
    VM = config.verification_messages
    role_mention = f"<@&{state['selected_role_id']}>" if state.get('selected_role_id') else "???"
    if user_id not in state['verified_by']:
        state['verified_by'].append(user_id)
    state['verifiers_done'] += 1
    state['last_verifier'] = mention
    remaining = state['verifiers_needed'] - state['verifiers_done']
    if remaining <= 0:
        await thread.send(VM["verif_complete"].format(role_mention=role_mention, mention=mention), allowed_mentions=_no_ping())
        await _complete_verification(thread, state, bot_msg)
        return
    _save_state()
    await thread.send(VM["verif_in_progress"].format(role_mention=role_mention, mention=mention, remaining=remaining), allowed_mentions=_no_ping())
    await _set_tags(thread, [TAG_NEEDS_VERIFICATION, _verifier_tag(remaining)])
    content = _build_challenge_message(state, thread.guild)
    await bot_msg.edit(content=content, view=VerificationView(remaining, hide_change=state['verifiers_done'] > 0), suppress=True)

# ── Flow functions ──────────────────────────────────────────────────────────

async def start_verification_flow(thread: discord.Thread):
    VM = config.verification_messages
    s = _init_state(thread.id, thread.owner_id)
    view = ChallengeCategoryView()
    msg = await thread.send(VM["flow_start"].format(op_id=thread.owner_id), view=view)
    s['message_id'] = msg.id
    _save_state()
    await _set_tags(thread, [TAG_PREPARING])

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
    video_url = _get_youtube_url(content) or content
    state['video_url'] = video_url
    _save_state()
    await _process_video(video_id, thread, state, bot_msg)

async def _ask_for_video(thread: discord.Thread, state: dict, bot_msg: discord.Message):
    VM = config.verification_messages
    op_id = state['op_id']
    content = _build_challenge_message(state, thread.guild)
    content += "\n\n" + VM["flow_ask_video"].format(op_id=op_id)
    view = NoFootageView()
    await bot_msg.edit(content=content, view=view, allowed_mentions=_no_ping())
    state['state'] = 'awaiting_video'
    _save_state()

async def _process_video(video_id: str, thread: discord.Thread, state: dict, bot_msg: discord.Message):
    status = await _check_youtube_video(video_id)
    if status == 'available':
        state['video_ready'] = True
        state['state'] = 'needs_verification'
        _save_state()
        await _enter_verification_phase(thread, state, bot_msg)
    else:
        state['state'] = 'awaiting_upload'
        state['next_check_at'] = _next_5min_interval()
        _save_state()
        await _set_tags(thread, [TAG_UPLOADING])
        content = _build_challenge_message(state, thread.guild)
        await bot_msg.edit(content=content, allowed_mentions=_no_ping(), suppress=True)
        if not video_polling_loop.is_running():
            video_polling_loop.start()

async def _enter_verification_phase(thread: discord.Thread, state: dict, bot_msg: discord.Message):
    VM = config.verification_messages
    needed = state['verifiers_needed']
    state['state'] = 'verification'
    _save_state()
    tag_ids = [TAG_NEEDS_VERIFICATION, _verifier_tag(needed)]
    await _set_tags(thread, tag_ids)
    content = _build_challenge_message(state, thread.guild)
    view = VerificationView(needed, hide_change=state['verifiers_done'] > 0)
    await bot_msg.edit(content=content, view=view, allowed_mentions=_no_ping(), suppress=True)
    if not state.get('verifier_pinged'):
        state['verifier_pinged'] = True
        _save_state()
        role = thread.guild.get_role(state['selected_role_id']) if state.get('selected_role_id') else None
        info = parse_challenge_role(role) if role else None
        name = info['name'] if info else "???"
        await thread.send(VM["verif_ping"].format(name=name, VERIFIER_ROLE_ID=VERIFIER_ROLE_ID))

async def _complete_verification(thread: discord.Thread, state: dict, bot_msg: discord.Message = None):
    VM = config.verification_messages
    state['state'] = 'verified'
    role_id = state['selected_role_id']
    op_id = state['op_id']
    _save_state()
    await _set_tags(thread, [TAG_VERIFIED])
    member = thread.guild.get_member(op_id)
    if member and role_id:
        async with RoleSession(member) as rs:
            rs.add(role_id)
    role_mention = f"<@&{role_id}>" if role_id else "???"
    last = state.get('last_verifier', 'someone')
    await thread.send(VM["verif_done_thread"].format(role_mention=role_mention, last=last), allowed_mentions=_no_ping())
    if bot_msg:
        try:
            role = thread.guild.get_role(role_id) if role_id else None
            info = parse_challenge_role(role) if role else None
            name = info['name'] if info else "???"
            op_mention = f"<@{op_id}>"
            final_lines = [
                VM["msg_header_title"].format(role_mention=role_mention),
                VM["msg_header_body"].format(op_mention=op_mention, name=name),
            ]
            if state.get('video_url'):
                final_lines.append(VM["msg_url_line"].format(url=state['video_url']))
            verified_by = state.get('verified_by', [])
            if verified_by:
                verifier_mentions = ", ".join(f"<@{uid}>" for uid in verified_by)
                final_lines.append(VM["msg_body_verified_by"].format(verifiers=verifier_mentions))
            final_lines.append("")
            final_lines.append(VM["verif_done_bot"].format(role_mention=role_mention))
            await bot_msg.edit(content="\n".join(final_lines), view=None, allowed_mentions=AllowedMentions.none())
        except discord.HTTPException:
            log.warning("verification: HTTP error swallowed", exc_info=True)
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
    state['video_url'] = _get_youtube_url(message.content) or message.content
    _save_state()
    try:
        bot_msg = await message.channel.fetch_message(state['message_id'])
    except discord.HTTPException:
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
    state['video_url'] = _get_youtube_url(after.content) or after.content
    _save_state()
    try:
        bot_msg = await after.channel.fetch_message(state['message_id'])
    except discord.HTTPException:
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
            await interaction.response.send_message(VM["err_not_op"], ephemeral=True)
            return
        state = _get_state(interaction.channel_id)
        state['selected_category'] = category
        state['menu_page'] = 0
        state['state'] = 'choose_challenge'
        _save_state()
        official, custom, joke = _get_challenge_roles(interaction.guild)
        roles = {'official': official, 'custom': custom, 'joke': joke}[category]
        view = ChallengeMenuView(category, roles, 0, interaction.guild)
        await interaction.response.edit_message(content=VM["flow_pick_challenge"], view=view)

    @discord.ui.button(label=VM["btn_official"], style=discord.ButtonStyle.secondary, custom_id="v:cat:off")
    async def official_btn(self, interaction: discord.Interaction, button: Button):
        await self._handle_category(interaction, 'official')

    @discord.ui.button(label=VM["btn_custom"], style=discord.ButtonStyle.secondary, custom_id="v:cat:cust")
    async def custom_btn(self, interaction: discord.Interaction, button: Button):
        await self._handle_category(interaction, 'custom')

    @discord.ui.button(label=VM["btn_joke"], style=discord.ButtonStyle.secondary, custom_id="v:cat:joke")
    async def joke_btn(self, interaction: discord.Interaction, button: Button):
        await self._handle_category(interaction, 'joke')

    @discord.ui.button(label=VM["btn_fail"], style=discord.ButtonStyle.danger, custom_id="v:cat:fail", row=1)
    async def fail_btn(self, interaction: discord.Interaction, button: Button):
        if not await self._is_op(interaction):
            await interaction.response.send_message(VM["err_not_op"], ephemeral=True)
            return
        state = _get_state(interaction.channel_id)
        state['state'] = 'ignore'
        state['ignore'] = True
        _save_state()
        thread = interaction.channel
        await _set_tags(thread, [])
        view = ReopenView()
        await interaction.response.edit_message(
            content=VM["flow_ignore"],
            view=view,
            allowed_mentions=_no_ping(),
        )


class ReopenView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label=VM["btn_reopen"], style=discord.ButtonStyle.primary, custom_id="v:reopen")
    async def reopen_btn(self, interaction: discord.Interaction, button: Button):
        state = _get_state(interaction.channel_id)
        if interaction.user.id != state['op_id']:
            await interaction.response.send_message(VM["err_not_op"], ephemeral=True)
            return
        state['state'] = 'choose_category'
        state['ignore'] = False
        _save_state()
        thread = interaction.channel
        await _set_tags(thread, [TAG_PREPARING])
        view = ChallengeCategoryView()
        await interaction.response.edit_message(
            content=VM["flow_pick_category"].format(op_mention=f"<@{state['op_id']}>"),
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
            ('official', VM["btn_tab_official"], 'v:tab:off'),
            ('custom', VM["btn_tab_custom"], 'v:tab:cust'),
            ('joke', VM["btn_tab_joke"], 'v:tab:joke'),
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
            options.append(discord.SelectOption(label=VM["no_challenges"], value="none"))
        select = Select(placeholder=VM["select_placeholder"], options=options, custom_id="v:menu")
        select.callback = self._on_select
        self.add_item(select)

        total_pages = max(1, -(-len(roles) // per_page))
        if total_pages > 1:
            prev_b = Button(label=VM["btn_prev"], style=discord.ButtonStyle.secondary, disabled=page == 0, custom_id="v:prev", row=2)
            next_b = Button(label=VM["btn_next"], style=discord.ButtonStyle.secondary, disabled=page >= total_pages - 1, custom_id="v:next", row=2)
            prev_b.callback = self._make_page_cb(-1)
            next_b.callback = self._make_page_cb(1)
            self.add_item(prev_b)
            self.add_item(next_b)

    def _make_tab_cb(self, category: str):
        async def cb(interaction: discord.Interaction):
            state = _get_state(interaction.channel_id)
            if interaction.user.id != state['op_id']:
                await interaction.response.send_message(VM["err_not_op"], ephemeral=True)
                return
            official, custom, joke = _get_challenge_roles(interaction.guild)
            roles = {'official': official, 'custom': custom, 'joke': joke}[category]
            state['selected_category'] = category
            state['menu_page'] = 0
            _save_state()
            await interaction.response.edit_message(content=VM["flow_pick_challenge"], view=ChallengeMenuView(category, roles, 0, interaction.guild))
        return cb

    def _make_page_cb(self, delta: int):
        async def cb(interaction: discord.Interaction):
            state = _get_state(interaction.channel_id)
            if interaction.user.id != state['op_id']:
                await interaction.response.send_message(VM["err_not_op"], ephemeral=True)
                return
            official, custom, joke = _get_challenge_roles(interaction.guild)
            cat = state.get('selected_category', 'official')
            roles = {'official': official, 'custom': custom, 'joke': joke}[cat]
            new_page = state['menu_page'] + delta
            state['menu_page'] = new_page
            _save_state()
            await interaction.response.edit_message(content=VM["flow_pick_challenge"], view=ChallengeMenuView(cat, roles, new_page, interaction.guild))
        return cb

    async def _on_select(self, interaction: discord.Interaction):
        state = _get_state(interaction.channel_id)
        if interaction.user.id != state['op_id']:
            await interaction.response.send_message(VM["err_not_op"], ephemeral=True)
            return
        val = interaction.data['values'][0]
        if val == 'none':
            await interaction.response.defer()
            return
        role_id = int(val)
        role = interaction.guild.get_role(role_id)
        if not role:
            await interaction.response.send_message(VM["err_role_not_found"], ephemeral=True)
            return
        info = parse_challenge_role(role)
        if not info:
            await interaction.response.send_message(VM["err_invalid_challenge"], ephemeral=True)
            return
        state['selected_role_id'] = role_id
        if not state.get('verifiers_needed'):
            state['verifiers_needed'] = _verifiers_for_points(info['points'])
        state['state'] = 'challenge_selected'
        _save_state()
        thread = interaction.channel
        if isinstance(thread, discord.Thread):
            op = thread.guild.get_member(state['op_id'])
            op_name = op.display_name if op else f"user-{state['op_id']}"
            new_name = f"{info['name']} by {op_name}"[:100]
            if info and info['points'] == 0:
                new_name = f"[JOKE BADGE] {new_name}"
            try:
                await thread.edit(name=new_name)
            except discord.HTTPException:
                log.warning("verification: HTTP error swallowed", exc_info=True)
        content = _build_challenge_message(state, interaction.guild)
        view = ChallengeConfirmView()
        await interaction.response.edit_message(content=content, view=view, allowed_mentions=_no_ping())
        if isinstance(thread, discord.Thread):
            try:
                starter = await thread.fetch_message(thread.id)
            except discord.HTTPException:
                starter = None
            if starter:
                await _handle_video_check(starter, thread, state, interaction.message)


class ChallengeConfirmView(View):
    def __init__(self):
        super().__init__(timeout=None)

        bv = Button(label=VM["btn_verify"].format(needed="X"), style=discord.ButtonStyle.success, disabled=True, custom_id="v:cfm:vrfy")
        bv.callback = self._dummy
        self.add_item(bv)

        br = Button(label=VM["btn_request_mod"], style=discord.ButtonStyle.secondary, disabled=True, custom_id="v:cfm:rpt")
        br.callback = self._dummy
        self.add_item(br)

        bc = Button(label=VM["btn_change"], style=discord.ButtonStyle.secondary, custom_id="v:cfg:change")
        bc.callback = self._on_change
        self.add_item(bc)

    async def _dummy(self, interaction: discord.Interaction):
        await interaction.response.defer()

    async def _on_change(self, interaction: discord.Interaction):
        state = _get_state(interaction.channel_id)
        if interaction.user.id != state['op_id']:
            await interaction.response.send_message(VM["err_not_op"], ephemeral=True)
            return
        if state.get('verifiers_done', 0) > 0:
            await interaction.response.send_message(VM["err_cant_change"], ephemeral=True)
            return
        official, custom, joke = _get_challenge_roles(interaction.guild)
        cat = state.get('selected_category', 'official')
        roles = {'official': official, 'custom': custom, 'joke': joke}[cat]
        state['state'] = 'choose_challenge'
        _save_state()
        view = ChallengeMenuView(cat, roles, 0, interaction.guild)
        await interaction.response.edit_message(content=VM["flow_pick_challenge"], view=view)


class NoFootageView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label=VM["btn_no_footage"], style=discord.ButtonStyle.danger, custom_id="v:nofoot")
    async def no_footage_btn(self, interaction: discord.Interaction, button: Button):
        state = _get_state(interaction.channel_id)
        if interaction.user.id != state['op_id']:
            await interaction.response.send_message(VM["err_not_op"], ephemeral=True)
            return
        state['no_footage'] = True
        state['state'] = 'needs_verification'
        _save_state()
        await _enter_verification_phase(interaction.channel, state, interaction.message)


class OwnerVerifyPromptView(View):
    def __init__(self, is_redo: bool):
        super().__init__()
        self.is_redo = is_redo

    @discord.ui.button(label=VM["btn_verify_anyway"], style=discord.ButtonStyle.primary)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        state = _get_state(interaction.channel_id)
        thread = interaction.channel
        user_id = interaction.user.id
        mention = interaction.user.mention
        try:
            bot_msg = await thread.fetch_message(state['message_id'])
        except discord.HTTPException:
            await interaction.response.edit_message(content=VM["err_no_bot_msg"], view=None)
            return
        await interaction.response.edit_message(content=VM["info_proceeding"], view=None)
        await _do_verify(thread, state, user_id, mention, bot_msg)

    @discord.ui.button(label=VM["btn_cancel"], style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content=VM["info_cancelled"], view=None)


class OwnerVerifySelfView(View):
    def __init__(self):
        super().__init__()

    @discord.ui.button(label=VM["btn_verify_self"], style=discord.ButtonStyle.primary)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        state = _get_state(interaction.channel_id)
        thread = interaction.channel
        user_id = interaction.user.id
        mention = interaction.user.mention
        try:
            bot_msg = await thread.fetch_message(state['message_id'])
        except discord.HTTPException:
            await interaction.response.edit_message(content=VM["err_no_bot_msg"], view=None)
            return
        await interaction.response.edit_message(content=VM["info_proceeding"], view=None)
        await _do_verify(thread, state, user_id, mention, bot_msg)

    @discord.ui.button(label=VM["btn_cancel"], style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content=VM["info_cancelled"], view=None)


class VerificationView(View):
    def __init__(self, verifiers_needed: int, hide_change: bool = False):
        super().__init__(timeout=None)

        vbtn = Button(label=VM["btn_verify"].format(needed=verifiers_needed), style=discord.ButtonStyle.success, custom_id="v:verify")
        vbtn.callback = self._on_verify
        self.add_item(vbtn)

        rbtn = Button(label=VM["btn_request_mod"], style=discord.ButtonStyle.secondary, custom_id="v:report")
        rbtn.callback = self._on_report
        self.add_item(rbtn)

        rjbtn = Button(label=VM["btn_reject"], style=discord.ButtonStyle.danger, custom_id="v:reject")
        rjbtn.callback = self._on_reject
        self.add_item(rjbtn)

        if not hide_change:
            cbtn = Button(label=VM["btn_change"], style=discord.ButtonStyle.secondary, custom_id="v:ver:change", row=1)
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
        if state.get('state') in ('reported', 'manual', 'rejected'):
            if state.get('state') == 'rejected':
                await interaction.response.send_message(VM["err_rejected"], ephemeral=True)
            else:
                await interaction.response.send_message(VM["err_locked"], ephemeral=True)
            return
        user = interaction.user
        if not isinstance(user, discord.Member):
            user = interaction.guild.get_member(user.id)
        if not user:
            await interaction.response.send_message(VM["err_no_identity"], ephemeral=True)
            return

        is_owner = user.id == interaction.guild.owner_id
        is_op = user.id == state['op_id']
        has_role = await self._is_verifier(interaction)
        already = user.id in state.get('verified_by', [])

        if not is_owner and not has_role:
            await interaction.response.send_message(VM["err_not_verifier"], ephemeral=True)
            return

        if is_op:
            if is_owner:
                prompt = OwnerVerifySelfView()
                await interaction.response.send_message(VM["prompt_self_verify_owner"], view=prompt, ephemeral=True)
                return
            else:
                await interaction.response.send_message(VM["err_self_verify"], ephemeral=True)
                return

        if already:
            if is_owner:
                prompt = OwnerVerifyPromptView(is_redo=True)
                await interaction.response.send_message(VM["prompt_redo_owner"], view=prompt, ephemeral=True)
            else:
                await interaction.response.send_message(VM["err_already_done"], ephemeral=True)
            return

        if is_owner and not has_role:
            prompt = OwnerVerifyPromptView(is_redo=False)
            await interaction.response.send_message(VM["prompt_owner_no_role"], view=prompt, ephemeral=True)
            return

        thread = interaction.channel
        try:
            bot_msg = await thread.fetch_message(state['message_id'])
        except discord.HTTPException:
            await interaction.response.send_message(VM["err_no_bot_msg"], ephemeral=True)
            return

        await _do_verify(thread, state, user.id, user.mention, bot_msg)

    async def _on_reject(self, interaction: discord.Interaction):
        state = _get_state(interaction.channel_id)
        if state.get('state') in ('reported', 'manual', 'rejected'):
            if state.get('state') == 'rejected':
                await interaction.response.send_message(VM["err_rejected"], ephemeral=True)
            else:
                await interaction.response.send_message(VM["err_locked"], ephemeral=True)
            return
        user = interaction.user
        if not isinstance(user, discord.Member):
            user = interaction.guild.get_member(user.id)
        has_role = await self._is_verifier(interaction)
        is_owner = interaction.guild.owner_id == user.id if user else False

        if not is_owner and not has_role:
            await interaction.response.send_message(VM["err_not_verifier"], ephemeral=True)
            return

        await interaction.response.send_message(
            VM["reject_prompt"],
            view=RejectConfirmView(),
            ephemeral=True,
        )

    async def _on_report(self, interaction: discord.Interaction):
        state = _get_state(interaction.channel_id)
        if state.get('state') in ('reported', 'manual', 'rejected'):
            await interaction.response.send_message(VM["err_locked"], ephemeral=True)
            return
        user = interaction.user
        if not isinstance(user, discord.Member):
            user = interaction.guild.get_member(user.id)
        is_owner = interaction.guild.owner_id == user.id if user else False
        has_role = await self._is_verifier(interaction)

        if not is_owner and not has_role:
            await interaction.response.send_message(VM["err_not_verifier"], ephemeral=True)
            return

        await interaction.response.send_message(
            VM["report_prompt"].format(MOD_ROLE_ID=MOD_ROLE_ID),
            view=ReportConfirmView(),
            ephemeral=True,
        )

    async def _on_change(self, interaction: discord.Interaction):
        state = _get_state(interaction.channel_id)
        if interaction.user.id != state['op_id']:
            await interaction.response.send_message(VM["err_not_op"], ephemeral=True)
            return
        if state.get('verifiers_done', 0) > 0:
            await interaction.response.send_message(VM["err_cant_change"], ephemeral=True)
            return
        official, custom, joke = _get_challenge_roles(interaction.guild)
        cat = state.get('selected_category', 'official')
        roles = {'official': official, 'custom': custom, 'joke': joke}[cat]
        state['state'] = 'choose_challenge'
        _save_state()
        view = ChallengeMenuView(cat, roles, 0, interaction.guild)
        await interaction.response.edit_message(content=VM["flow_pick_challenge"], view=view)


class ReportConfirmView(View):
    def __init__(self):
        super().__init__()

    @discord.ui.button(label=VM["btn_escalate"], style=discord.ButtonStyle.danger)
    async def confirm_btn(self, interaction: discord.Interaction, button: Button):
        state = _get_state(interaction.channel_id)
        state['state'] = 'reported'
        _save_state()
        thread = interaction.channel
        await _set_tags(thread, [TAG_REPORTED])
        role_mention = f"<@&{state['selected_role_id']}>" if state.get('selected_role_id') else "???"
        content = _build_challenge_message(state, interaction.guild)
        await interaction.response.edit_message(content=VM["report_escalated"], view=None)
        main_msg = thread.get_partial_message(state['message_id'])
        try:
            await main_msg.edit(content=content, view=ReportResolveView())
        except discord.HTTPException:
            log.warning("verification: HTTP error swallowed", exc_info=True)
        await thread.send(VM["report_notify"].format(MOD_ROLE_ID=MOD_ROLE_ID, role_mention=role_mention))

    @discord.ui.button(label=VM["btn_cancel"], style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content=VM["report_cancelled"], view=None)


class ReportResolveView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label=VM["btn_resolve"], style=discord.ButtonStyle.primary, custom_id="v:resolve")
    async def resolve_btn(self, interaction: discord.Interaction, button: Button):
        if not await _check_mod(interaction):
            return
        state = _get_state(interaction.channel_id)
        state['state'] = 'verification'
        state['report_resolved'] = True
        _save_state()
        thread = interaction.channel
        remaining = state['verifiers_needed'] - state['verifiers_done']
        await _set_tags(thread, [TAG_NEEDS_VERIFICATION, _verifier_tag(remaining)])
        content = _build_challenge_message(state, interaction.guild)
        view = VerificationView(remaining, hide_change=state['verifiers_done'] > 0)
        await interaction.response.edit_message(content=content, view=view, allowed_mentions=_no_ping())
        await thread.send(VM["report_resolved"].format(mention=interaction.user.mention), allowed_mentions=_no_ping())

    @discord.ui.button(label=VM["btn_manual_enter"], style=discord.ButtonStyle.secondary, custom_id="v:manual:enter")
    async def manual_btn(self, interaction: discord.Interaction, button: Button):
        if not await _check_mod(interaction):
            return
        state = _get_state(interaction.channel_id)
        state['state'] = 'manual'
        state['report_resolved'] = True
        _save_state()
        thread = interaction.channel
        await _set_tags(thread, [TAG_REPORTED, TAG_MANUAL])
        content = _build_challenge_message(state, interaction.guild)
        content += VM["flow_manual_desc"]
        await interaction.response.edit_message(content=content, view=ManualModeView(), allowed_mentions=_no_ping())
        await thread.send(VM["manual_activated"].format(mention=interaction.user.mention), allowed_mentions=_no_ping())


class RejectConfirmView(View):
    def __init__(self):
        super().__init__()

    @discord.ui.button(label=VM["btn_reject"], style=discord.ButtonStyle.danger)
    async def confirm_btn(self, interaction: discord.Interaction, button: Button):
        state = _get_state(interaction.channel_id)
        state['state'] = 'rejected'
        state['rejected'] = True
        _save_state()
        thread = interaction.channel
        await _set_tags(thread, [TAG_REJECTED])
        content = _build_challenge_message(state, interaction.guild)
        await interaction.response.edit_message(content=VM["info_proceeding"], view=None)
        main_msg = thread.get_partial_message(state['message_id'])
        try:
            await main_msg.edit(content=content, view=RejectResolveView())
        except discord.HTTPException:
            log.warning("verification: HTTP error swallowed", exc_info=True)
        await thread.send(VM["reject_notify"].format(mention=interaction.user.mention))
        await thread.edit(archived=True, locked=True)
        _clean_state(thread.id)

    @discord.ui.button(label=VM["btn_cancel"], style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content=VM["reject_cancelled"], view=None)


class RejectResolveView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label=VM["btn_reinstate"], style=discord.ButtonStyle.primary, custom_id="v:reinstate")
    async def reinstate_btn(self, interaction: discord.Interaction, button: Button):
        if not await _check_mod(interaction):
            return
        state = _get_state(interaction.channel_id)
        state['state'] = 'verification'
        state['rejected'] = False
        _save_state()
        thread = interaction.channel
        remaining = state['verifiers_needed'] - state['verifiers_done']
        await _set_tags(thread, [TAG_NEEDS_VERIFICATION, _verifier_tag(remaining)])
        content = _build_challenge_message(state, interaction.guild)
        view = VerificationView(remaining, hide_change=state['verifiers_done'] > 0)
        await interaction.response.edit_message(content=content, view=view, allowed_mentions=_no_ping())
        await thread.send(VM["rejected_resolved"].format(mention=interaction.user.mention), allowed_mentions=_no_ping())


class ManualModeView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label=VM["btn_manual_exit"], style=discord.ButtonStyle.secondary, custom_id="v:manual:exit")
    async def exit_btn(self, interaction: discord.Interaction, button: Button):
        if not await _check_mod(interaction):
            return
        state = _get_state(interaction.channel_id)
        state['state'] = 'verification'
        state['report_resolved'] = True
        _save_state()
        thread = interaction.channel
        remaining = state['verifiers_needed'] - state['verifiers_done']
        await _set_tags(thread, [TAG_NEEDS_VERIFICATION, _verifier_tag(remaining)])
        content = _build_challenge_message(state, interaction.guild)
        view = VerificationView(remaining, hide_change=state['verifiers_done'] > 0)
        await interaction.response.edit_message(content=content, view=view, allowed_mentions=_no_ping())
        await thread.send(VM["manual_exit"].format(mention=interaction.user.mention), allowed_mentions=_no_ping())

    @discord.ui.button(label=VM["btn_manual_verify_no_roles"], style=discord.ButtonStyle.success, custom_id="v:manual:verify")
    async def verify_no_roles_btn(self, interaction: discord.Interaction, button: Button):
        if not await _check_mod(interaction):
            return
        state = _get_state(interaction.channel_id)
        thread = interaction.channel
        role_mention = f"<@&{state['selected_role_id']}>" if state.get('selected_role_id') else "???"
        await interaction.response.edit_message(content=VM["verif_done_bot"].format(role_mention=role_mention), view=None, allowed_mentions=_no_ping())
        await thread.send(VM["manual_verify_no_roles"].format(role_mention=role_mention, mention=interaction.user.mention), allowed_mentions=_no_ping())
        await thread.edit(archived=True, locked=True)
        _clean_state(thread.id)

    @discord.ui.button(label=VM["btn_manual_verify_roles"], style=discord.ButtonStyle.primary, custom_id="v:manual:verify_roles")
    async def verify_with_roles_btn(self, interaction: discord.Interaction, button: Button):
        if not await _check_mod(interaction):
            return
        state = _get_state(interaction.channel_id)
        thread = interaction.channel
        role_id = state['selected_role_id']
        op_id = state['op_id']
        state['state'] = 'verified'
        _save_state()
        await _set_tags(thread, [TAG_VERIFIED])
        member = thread.guild.get_member(op_id)
        if member and role_id:
            async with RoleSession(member) as rs:
                rs.add(role_id)
        role_mention = f"<@&{role_id}>" if role_id else "???"
        await interaction.response.edit_message(content=VM["verif_done_bot"].format(role_mention=role_mention), view=None, allowed_mentions=_no_ping())
        await thread.send(VM["manual_verify_roles"].format(role_mention=role_mention, mention=interaction.user.mention), allowed_mentions=_no_ping())
        await thread.edit(archived=True, locked=True)
        _clean_state(thread.id)


# ── Polling ─────────────────────────────────────────────────────────────────

@tasks.loop(minutes=5)
async def video_polling_loop():
    now = int(time.time())
    next_check = ((now // 300) + 1) * 300
    for key, s in list(_state.items()):
        try:
            if s.get('state') != 'awaiting_upload':
                continue
            video_url = s.get('video_url')
            if not video_url:
                continue
            video_id = _get_youtube_video_id(video_url)
            if not video_id:
                continue
            status = await _check_youtube_video(video_id)
            if status == 'available':
                thread = bot.get_channel(s['thread_id'])
                if not isinstance(thread, discord.Thread):
                    try:
                        thread = await bot.fetch_channel(s['thread_id'])
                    except discord.HTTPException:
                        continue
                    if not isinstance(thread, discord.Thread):
                        continue
                try:
                    msg = await thread.fetch_message(s['message_id'])
                except discord.HTTPException:
                    continue
                s['video_ready'] = True
                _save_state()
                await _enter_verification_phase(thread, s, msg)
            else:
                s['next_check_at'] = next_check
                _save_state()
                try:
                    thread = bot.get_channel(s['thread_id'])
                    if not isinstance(thread, discord.Thread):
                        thread = await bot.fetch_channel(s['thread_id'])
                    if not isinstance(thread, discord.Thread):
                        continue
                    msg = await thread.fetch_message(s['message_id'])
                    content = _build_challenge_message(s, thread.guild)
                    await msg.edit(content=content, allowed_mentions=_no_ping(), suppress=True)
                except discord.HTTPException:
                    log.warning("verification: HTTP error swallowed", exc_info=True)
        except Exception:
            log.exception("video_polling_loop: transient error swallowed; loop continues")


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
    client.add_view(ManualModeView())
    client.add_view(ReportResolveView())
    client.add_view(RejectResolveView())

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
            except discord.HTTPException:
                log.warning("verification: HTTP error swallowed", exc_info=True)
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
        if s.get('verifier_pinged'):
            s['state'] = 'verification'
            _save_state()
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
        except discord.HTTPException:
            continue
        s['video_ready'] = True
        _save_state()
        try:
            await _enter_verification_phase(thread, s, bot_msg)
        except Exception:
            log.exception("restore_sessions: failed to restore one verification session")
