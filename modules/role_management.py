import re

import discord
from modules import config

RELATIONS_CHANNEL_ID = 1503134832719302866
_role_relations: dict[int, list[int]] = {}


# ── relation loading ────────────────────────────────────────────────────────


def _parse_relations_from_text(content: str) -> dict[int, list[int]]:
    relations: dict[int, list[int]] = {}
    current_parent: int | None = None

    for line in content.splitlines():
        if m := re.match(r"^- <@&(\d+)>\s*$", line):
            current_parent = int(m.group(1))
            relations.setdefault(current_parent, [])
        elif m := re.match(r"^\s+- <@&(\d+)>\s*$", line):
            if current_parent is not None:
                relations[current_parent].append(int(m.group(1)))
        elif line.strip():
            # Non-empty, non-bullet line → comment/header, reset context
            current_parent = None

    return relations


async def load_role_relations(bot: discord.Client) -> None:
    """
    Reads the role-relations channel and caches the parsed graph.
    Call once at startup (and again whenever you want to refresh).
    """
    global _role_relations
    channel = bot.get_channel(RELATIONS_CHANNEL_ID)
    if not channel:
        return

    combined: dict[int, list[int]] = {}
    async for message in channel.history(limit=None):
        for parent, children in _parse_relations_from_text(
            message.content
        ).items():
            combined.setdefault(parent, []).extend(children)

    _role_relations = combined


# ── internal helpers ────────────────────────────────────────────────────────


def _get_role_hierarchy(guild: discord.Guild):
    # categories[category_role] = { 'roles': [list], 'none_role': discord.Role or None }
    categories = {}
    current_category = None

    sorted_roles = sorted(guild.roles, key=lambda r: r.position, reverse=True)

    for role in sorted_roles:
        if role.name.startswith("──╱") and role.name.endswith("─"):
            current_category = role
            categories[current_category] = {"roles": [], "none_role": None}
            continue

        if current_category:
            if role.is_default():  # stop at @everyone
                current_category = None
                continue
            if role.name == "🚫 none":
                categories[current_category]["none_role"] = role
            elif role.name.strip() == "":
                continue
            else:
                categories[current_category]["roles"].append(role)

    return categories


def _fix_categories(current_roles: set, guild: discord.Guild) -> set:
    hierarchy = _get_role_hierarchy(guild)

    for cat_role, data in hierarchy.items():
        sub_roles = set(data["roles"])
        none_role = data["none_role"]
        has_sub_roles = any(r in current_roles for r in sub_roles)

        if has_sub_roles:
            current_roles.add(cat_role)
            if none_role:
                current_roles.discard(none_role)
        else:
            if none_role:
                current_roles.add(cat_role)
                current_roles.add(none_role)
            else:
                current_roles.discard(cat_role)

    return current_roles


def _ensure_roles(current_roles: set, guild: discord.Guild) -> set:
    def has(role_id):
        return any(r.id == role_id for r in current_roles)

    def update(role_id, condition):
        role = guild.get_role(role_id)
        if not role:
            return
        if condition:
            current_roles.add(role)
        else:
            current_roles.discard(role)

    is_leader = has(config.roles["leader"])
    is_available = has(config.roles["available"])
    is_inactive = has(config.roles["inactive"])

    update(
        config.roles["in_vc_leader"], is_leader and has(config.roles["in_vc"])
    )
    update(
        config.roles["in_vc_2_leader"],
        is_leader and has(config.roles["in_vc_2"]),
    )
    update(
        config.roles["in_vc_3_leader"],
        is_leader and has(config.roles["in_vc_3"]),
    )
    update(config.roles["available_leader"], is_leader and is_available)

    update(
        config.roles["available_not_in_vc"],
        is_available and not has(config.roles["in_vc"]),
    )
    update(
        config.roles["available_not_in_vc_2"],
        is_available and not has(config.roles["in_vc_2"]),
    )
    update(
        config.roles["available_not_in_vc_3"],
        is_available and not has(config.roles["in_vc_3"]),
    )

    update(
        config.roles["not_available"], not is_available and not is_inactive
    )

    if is_inactive:
        update(config.roles["person"], False)
    else:
        update(config.roles["explained_inactive"], False)
        update(config.roles["person"], True)

    return current_roles


def _apply_role_relations(
    final_roles: set[discord.Role], guild: discord.Guild
) -> set[discord.Role]:
    """
    Transitively expands final_roles using the cached relation graph:
    for every parent role present, its child roles are added (recursively).
    """
    role_ids = {r.id for r in final_roles}
    queue = list(role_ids)
    visited: set[int] = set()

    while queue:
        r_id = queue.pop()
        if r_id in visited:
            continue
        visited.add(r_id)

        for child_id in _role_relations.get(r_id, []):
            if child_id not in role_ids:
                role = guild.get_role(child_id)
                if role:
                    final_roles.add(role)
                    role_ids.add(child_id)
                    queue.append(child_id)

    return final_roles


def _resolve_to_id(role_input) -> int | None:
    if isinstance(role_input, discord.Role):
        return role_input.id
    if isinstance(role_input, int):
        return role_input
    if isinstance(role_input, str):
        return config.roles.get(role_input)
    return None


# ── session ─────────────────────────────────────────────────────────────────


class RoleSession:
    def __init__(self, member: discord.Member, autocommit: bool = True):
        self.member = member
        self.guild = member.guild
        self.autocommit = autocommit
        self.to_add = set()
        self.to_remove = set()


    def add(self, *roles):
        for r in roles:
            r_id = _resolve_to_id(r)
            if r_id:
                self.to_add.add(r_id)
                self.to_remove.discard(r_id)

    def remove(self, *roles):
        for r in roles:
            r_id = _resolve_to_id(r)
            if r_id:
                self.to_remove.add(r_id)
                self.to_add.discard(r_id)


    def _build_final_roles(
        self, fresh_member: discord.Member
    ) -> set[discord.Role]:
        final_roles = set(fresh_member.roles)
        for r_id in self.to_add:
            role = self.guild.get_role(r_id)
            if role:
                final_roles.add(role)
        for r_id in self.to_remove:
            role = self.guild.get_role(r_id)
            if role:
                final_roles.discard(role)
        return final_roles


    def _apply_bot_roles(
        self, final_roles: set[discord.Role]
    ) -> set[discord.Role]:
        bot_role = self.guild.get_role(config.roles["bot"])
        person_role = self.guild.get_role(config.roles["person"])
        if bot_role:
            final_roles.add(bot_role)
        if person_role:
            final_roles.discard(person_role)
        return final_roles


    async def commit(self):
        fresh_member = self.guild.get_member(self.member.id)
        if not fresh_member:
            return

        final_roles = self._build_final_roles(fresh_member)

        if not self.member.bot:
            final_roles = _apply_role_relations(final_roles, self.guild)
            final_roles = _ensure_roles(final_roles, self.guild)
            final_roles = _fix_categories(final_roles, self.guild)
        else:
            final_roles = self._apply_bot_roles(final_roles)

        if final_roles != set(fresh_member.roles):
            await fresh_member.edit(roles=list(final_roles))


    # async def commit_with_relations(self):
    #     fresh_member = self.guild.get_member(self.member.id)
    #     if not fresh_member:
    #         return
    #
    #     final_roles = self._build_final_roles(fresh_member)
    #
    #     if not self.member.bot:
    #         final_roles = _apply_role_relations(final_roles, self.guild)
    #         final_roles = _ensure_roles(final_roles, self.guild)
    #         final_roles = _fix_categories(final_roles, self.guild)
    #     else:
    #         final_roles = self._apply_bot_roles(final_roles)
    #
    #     if final_roles != set(fresh_member.roles):
    #         await fresh_member.edit(roles=list(final_roles))


    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.autocommit and exc_type is None:
            await self.commit()