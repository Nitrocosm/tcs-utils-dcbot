import discord
from modules import config
from modules.general import send
from modules.role_management import RoleSession

SAVE_COOLDOWN = {}  # {user_id: datetime.datetime of last save}

SAVE_CATEGORY_NAME = "──／ saves ／──────────"
SAVE_CHANNEL_TEMPLATE = "💾┃save-{num}"
SAVE_ROLE_TEMPLATE = "💾 save {num}"


async def create_save(ctx, members: list[discord.Member], save_name: str = None):
    guild = ctx.guild

    # cooldown abuse protection
    import datetime
    now = datetime.datetime.now(datetime.UTC)
    user_id = ctx.author.id
    last_use = SAVE_COOLDOWN.get(user_id)

    if not ctx.author == ctx.guild.owner:
        if last_use:
            diff = (now - last_use).total_seconds()
            if diff < 120:
                if diff < 60:
                    return await ctx.send("nuh uh ur using ts too fast wait a bit")
                else:
                    await send(ctx.bot,
                               f"<@&{config.roles['mod']}> `{ctx.author.display_name}` is very sus they seem to abuse the save cmd")
        SAVE_COOLDOWN[user_id] = now

    # ensure "saves" category exists
    save_category: discord.CategoryChannel = discord.utils.get(guild.categories, name=SAVE_CATEGORY_NAME)
    if not save_category:
        save_category = await guild.create_category(
            SAVE_CATEGORY_NAME,
            reason="automatically created for save channels",
        )
        await save_category.edit(position=3)

    # find next save number
    existing_saves = [
        role for role in guild.roles if role.name.startswith("💾 save ")
    ]
    existing_nums = [
        int(role.name.split()[2])
        for role in existing_saves
        if role.name.split()[2].isdigit()
    ]
    new_num = max(existing_nums, default=0) + 1

    # create role
    save_role = await guild.create_role(
        name=SAVE_ROLE_TEMPLATE.format(num=new_num),
        reason="new save group created",
        mentionable=True
    )

    # assign role to members
    for m in members:
        async with RoleSession(m) as rs:
            rs.add(save_role.id)
            # manual category removal removed: RoleSession._fix_categories handles this now

    # create channel name
    if save_name:
        save_name = save_name.replace(" ", "-")
        channel_name = f"💾┃save-{new_num}┃{save_name}"
    else:
        channel_name = SAVE_CHANNEL_TEMPLATE.format(num=new_num)

    # create text channel
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        save_role: discord.PermissionOverwrite(read_messages=True),
    }
    text_channel = await guild.create_text_channel(
        channel_name,
        category=save_category,
        overwrites=overwrites,
        reason="private save channel",
    )

    pinned_msg = await text_channel.send(
        f"# hi save group {new_num}\n"
        f"saved run with members {' '.join([m.mention for m in members])}\n"
        f"use this to coordinate or discuss your latest run!\n"
        f"**careful**: this channel is temporary and should be deleted when you are done with the run\n"
        f"additionally pls know that the owner has access to this channel at all times regardless of permissions, it's just a discord thing\n"
        f"**to remove this save, use `.disband` in this channel**\n"
        f"**to rename this save, use `.rename [name]` in this channel**\n"
    )
    await pinned_msg.pin()

    return await ctx.send(
        f"created {save_role.mention} with {len(members)} members :white_check_mark:\n"
        f"-# go to channel {text_channel.mention}"
    )


async def disband_save(ctx):
    channel = ctx.channel
    guild = ctx.guild
    if not channel.category or channel.category.name != SAVE_CATEGORY_NAME:
        return await ctx.send("this command only works inside save channels")

    # Extract save number from channel name
    parts = channel.name.split("┃")
    if len(parts) < 2 or not parts[1].startswith("save-"):
        return await ctx.send("couldn't parse save number, deleting channel anyway")

    number = parts[1].replace("save-", "")
    role_name = f"💾 save {number}"

    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        return await ctx.send("couldn't find corresponding role for this save, deleting channel anyway")


    # remove role and re-add misc none if needed
    await send(f"🗑️ {ctx.author.mention} disbanded the save number {number} {role.mention}")

    try:
        await role.delete(reason="save disbanded")
    except discord.Forbidden:
        ...

    await channel.delete(reason="save disbanded")

    # check if category now has no other channels
    if not channel.category.channels:
        await channel.category.delete(reason="no saves left")

    return None


async def rename_save(ctx, name: str = None):
    channel = ctx.channel

    if not channel.category or channel.category.name != SAVE_CATEGORY_NAME:
        return await ctx.send("this command only works inside save channels")

    # Extract save number from current channel name
    parts = channel.name.split("┃")
    if len(parts) < 2 or not parts[1].startswith("save-"):
        return await ctx.send("couldn't parse the save number from this channel")

    save_num = parts[1].replace("save-", "")

    # Create new channel name
    if name:
        name = name.replace(" ", "-")
        new_name = f"💾┃save-{save_num}┃{name}"
    else:
        new_name = f"💾┃save-{save_num}"

    try:
        await channel.edit(name=new_name)
        if name:
            await ctx.send(f"renamed save to `{name}` :white_check_mark:")
        else:
            await ctx.send("removed custom name :white_check_mark:")
    except discord.Forbidden:
        await ctx.send("i don't have permissions to rename this channel")
    except discord.HTTPException as e:
        await ctx.send(f"failed to rename: {e}")
