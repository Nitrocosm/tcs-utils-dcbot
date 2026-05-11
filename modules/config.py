from discord.ext import commands

TARGET_GUILD = 1426972810332340406

def check_guild(guild_id: int) -> bool:
    if guild_id == TARGET_GUILD:
        return True
    return False

from dotenv import dotenv_values
TOKEN = dotenv_values('.env').get('TOKEN')
if not TOKEN:
    print('there\'s no token\n'
          'create a .env file in this directory and put in "TOKEN=..." and replace the "..." with ur bot token')

roles = {
    "admins": [
        1427016174444613804, # the man behind the challenge
        1433828741548740781  # moderator
    ],
    "new_people": [
        1445189559200776302, # cat: activity
        1442132238660796416, # not available
        1445190367006818324, # cat: common
        1433872100837425193, # newbie
        1427076669264498820, # person
        1445134463263707156, # cat: badges
        1445191573305425930, # none
        1445191426920153159, # cat: misc
        1445191748010770493, # none
    ],
    "role_check": [
        1445189559200776302, # cat: activity
        1445190367006818324, # cat: common
        1445134463263707156, # cat: badges
        1445191426920153159, # cat: misc
    ],

    "bot": 1442086763161194597,
    "leader": 1426973394099896507,


    "in_vc_leader": 1427076452477702191,
    "in_vc_2_leader": 1444027828898238605,
    "in_vc_3_leader": 1464748454193659967,

    "in_vc": 1427076261586669688,
    "in_vc_2": 1444027810594295908,
    "in_vc_3": 1464748438754295975,

    "available_leader": 1434629548347232326,
    "available": 1434629510031999269,
    "available_not_in_vc": 1442132263071645779,
    "available_not_in_vc_2": 1444027740352155688,
    "available_not_in_vc_3": 1464748458698211338,
    "not_available": 1442132238660796416,


    "birthday": 1439339439762444552,
    "inactive": 1434659281822679232,
    "explained_inactive": 1444665652450169036,
    "person": 1427076669264498820,
    "newbie": 1433872100837425193,
    "warn_1": 1442596622013038704,
    "warn_2": 1442596750576717905,
    "warn_3": 1442623000452005948,
    "mod": 1433828741548740781,
    "spoiler": 1451675068114669740,

    # leaderboard display badges (user-chosen)
    "lb_display_top_1": 1469749458777538776,
    "lb_display_top_2": 1469749287196950826,
    "lb_display_top_3": 1469749290116190459,
    "lb_display_not_top": 1469749283946500119,

    # leaderboard normal badges (auto-assigned)
    "lb_top_1": 1469749299943440447,
    "lb_top_2": 1469749302636056759,
    "lb_top_3": 1469749305697898750,

    # completion roles
    "completion_all_base": 1453450000297365576,
    "completion_all_ultimate": 1454594165857063004,

    "completion_server_star_star": 1454594165857063004,
    "completion_server_base_star": 1453450000297365576
}

# def get_starting_roles(bot: commands.Bot):
#     for role_id in roles["new_people"]:
#         role = bot.get_guild(TARGET_GUILD).get_role(role_id)




channels = {
    "vc": 1426972811293098015,
    "vc2": 1444027467290513448,
    "vc3": 1464741550482264064,
    "chat": 1426972811293098014,
    "availability": 1434653852367585300,
    "availability_message": 1434654321886363658,
    "availability_reaction": 1439620553572089900,
    "ps_link": 1426974154556702720,
    "best_runs": 1427066908812906526,
    "mod_chat": 1442499917728976917,
    "leader_chat": 1453699078977224876,
    "logs_channel": 1453370470584815697,
    "spoiler": 1451673464359358465,
    "spoiler_access": 1451675640771383478,
    "spoiler_role": 1451675068114669740,
    "leaderboard": 1456353494448734331,
}

emoji = {
    "join": "<:join:1436503008924926052>",
    "leave": "<:leave:1436503027937841173>",
    "ban": "<:ban:1438882547588141118>",
    "kick": "<:kick:1439803052826689537>",
    "app_join": "<:newapp:1438882548829913209>",
    "app_leave": "<:removedapp:1438882550075621538>",
    "available": "<:available:1436525036281532449>",
    "unavailable": "<:notavailable:1436528517956374578>",
    "join_vc": "<:join_vc:1436503046107566181>",
    "leave_vc": "<:leave_vc:1436528566174220289>",
    "join_vc_2": "<:join_vc_2:1444102928880242709>",
    "leave_vc_2": "<:leave_vc_2:1444327229210497237>",
    "join_vc_3": "<:join_vc_3:1464759555199078474>",
    "promotion": "<:promotion:1442087863347974294>",
    "demotion": "<:demotion:1442087886391607376>",
    "birthday": "",
    "leader": "<:leader:1436531052670619791>",
    "death": "<:death:1436531054704852993>",
    "disconnect": "<:disconnected:1439792812165038080>",
    "blank": "<:blank:1436531505831612456>",
    "tcs": "<:this_challenge_sucks:1440645344252792922>",
    "gor": "<:group_of_rushers:1443250418418188402>",
    "pdo": "<:professional_door_opener:1443719522908504215>",
    "nn": "<:neverending_night:1443768885097529394>",
    "edit": "<:edit:1444529076516688064>",
    "edit_g": "<:edit_g:1464760651120509072>",
    "edit_p": "<:edit_p:1464760669596553246>",
    "edit_r": "<:edit_r:1464760671031005396>",
    "newbie": "<:upvote:1434612815062237195>",
    "inactive": "🛌",
    "inactive_revoke": "🏆",
    "explained_inactive": "✅",

    "knife": "🔪",
    "hug": "🤗",
    "kiss": "💋",
    "high_five": "✋",
    "handshake": "🤝",
    "fire": "🔥",
    "punch": "👊",
    "slap": "👋",
    "pat": "🫳",
    "touch": "👉",

    "lb_top_1": "<:leaderboard_top_1:1469760932950573117>",
    "lb_top_2": "<:leaderboard_top_2:1470181634111443217>",
    "lb_top_3": "<:leaderboard_top_3:1470181674804580422>",

    "star_completion": "<:star_completion:1453452694592159925>",
    "star_pure_completion": "<:star_pure_completion:1453452636618752214>",

    '0': '<:0_:1444462399632445473>',
    '1': '<:1_:1444462401075548353>',
    '2': '<:2_:1444462402312736962>',
    '3': '<:3_:1444462403902505134>',
    '4': '<:4_:1444462405286629618>',
    '5': '<:5_:1444462406779801734>',
    '6': '<:6_:1444462407962329088>',
    '7': '<:7_:1444462409342255204>',
    '8': '<:8_:1444462410584035388>',
    '9': '<:9_:1444462412559290492>',

    '0b': '<:0b:1448879492884861040>',
    '0g': '<:0g:1448879494063587509>',
    '0p': '<:0p:1448879495393054891>',
    '0r': '<:0r:1464759439784411166>',
    '1b': '<:1b:1448879496374779945>',
    '1g': '<:1g:1448879497838334122>',
    '1p': '<:1p:1448879499184705679>',
    '1r': '<:1r:1464759440795369472>',
    '2b': '<:2b:1448879500711690512>',
    '2g': '<:2g:1448879502422835452>',
    '2p': '<:2p:1448879504490762390>',
    '2r': '<:2r:1464759441911185469>',
    '3b': '<:3b:1448879506612813926>',
    '3g': '<:3g:1448879507753668638>',
    '3p': '<:3p:1448879508827672656>',
    '3r': '<:3r:1464759444322652443>',
    '4b': '<:4b:1448879509934964942>',
    '4g': '<:4g:1448879511205707796>',
    '4p': '<:4p:1448879512350887996>',
    '4r': '<:4r:1464759445442789579>',
    '5b': '<:5b:1448879513755979848>',
    '5g': '<:5g:1448879515206942771>',
    '5p': '<:5p:1448879516561702913>',
    '5r': '<:5r:1464759447422369803>',
    '6b': '<:6b:1448879517950017616>',
    '6g': '<:6g:1448879519942316132>',
    '6p': '<:6p:1448879521708376237>',
    '6r': '<:6r:1464759448584327339>',
    '7b': '<:7b:1448879523016872042>',
    '7g': '<:7g:1448879524350787775>',
    '7p': '<:7p:1448879526485426336>',
    '7r': '<:7r:1464759449666322493>',
    '8b': '<:8b:1448879527634931843>',
    '8g': '<:8g:1448879528825847951>',
    '8p': '<:8p:1448879529878618213>',
    '8r': '<:8r:1464759450765230133>',
    '9b': '<:9b:1448879531162210413>',
    '9g': '<:9g:1448879532508451019>',
    '9p': '<:9p:1448879535033421935>',
    '9r': '<:9r:1464759452316991619>'
}

_messages = {
    "join": [
        f"{emoji['join']} {{mention}}, are you ready for the pain?",
        f"{emoji['join']} {{mention}} should now prepare to die in the backdoor a hundred times",
        f"{emoji['join']} heya, {{mention}}, welcome! mind you, this entire server is a safespot",
        f"{emoji['join']} it's time for {{mention}} to acknowledge the possibility of pain and seizure",
        f"{emoji['join']} {{mention}} just joined! quick, everyone look like we know what we're doing!",
        f"{emoji['join']} uhh, hey, {{mention}}, you have any sanity? We're running low, could we please borrow some?",
        f"{emoji['join']} let's hope {{mention}} has it all Figured out"
    ],
    "join_bot": [
        f"{emoji['app_join']} someone added a clanker who goes by {{mention}}",
        f"{emoji['app_join']} i think {{mention}} just hacked us",
        f"{emoji['app_join']} {{mention}} computed its way in"
    ],
    "leave": [
        f"{emoji['leave']} {{mention}} ({{display}}) couldn't handle The Backdoor any longer...",
        f"{emoji['leave']} {{mention}} ({{display}}) disconnected. Please check your internet connection and try again. (Error Code: 277)",
        f"{emoji['leave']} {{mention}} ({{display}}) ran out of crucifixes, I guess...",
        f"{emoji['leave']} {{mention}} ({{display}}) ragequit",
        f"{emoji['leave']} {{mention}} ({{display}}) saw the light. it was outside. outside this server. they're happier now",
        f"{emoji['leave']} well off {{mention}} ({{display}}) goes ig"
    ],
    "kick": [
        f"{emoji['kick']} {{mention}} ({{display}}) was kicked from this experience (Error Code: 267)",
        f"{emoji['kick']} {{mention}} ({{display}}) slipped on a nanner peel placed by a mod and fell out of bounds",
        f"{emoji['kick']} an mod's mighty foot sent {{mention}} ({{display}}) flying. a reminder that you shouldn't fly during the challenge, that's cheating",
        f"{emoji['kick']} {{mention}} ({{display}}) got electrocuted. not by surge, though",
        f"{emoji['kick']} {{mention}} ({{display}}) got Figured out. by a mod."
    ],
    "ban": [
        f"{emoji['ban']} {{mention}} ({{display}}) got banned (ay yo)",
        f"{emoji['ban']} {{mention}} ({{display}}) was kicked from this experience: You have been permanently blacklisted from This Challenge Sucks (Error Code: 267)",
        f"{emoji['ban']} a mod got very angry and decided to ban {{mention}} ({{display}})"
    ],
    "kick_bot": [
        f"{emoji['app_leave']} well off {{mention}} goes ig",
        f"{emoji['app_leave']} bot {{mention}} was removed",
        f"{emoji['app_leave']} {{mention}} got disconnected"
    ],
    "spoiler_add": [f"{emoji['join']} {{mention}} joined the spoilers channel"],
    "spoiler_remove": [f"{emoji['kick']} {{mention}} is no longer in the spoilers channel"],

    "available": [f"{emoji['available']} **{{name}}** is now available {{available_count}}"],
    "available_ping": [f"{emoji['available']} **{{name}}** is now available {{available_count}} *<@&{roles['available']}>*"],

    "unavailable": [f"{emoji['unavailable']} **{{name}}** is no longer available {{available_count}}"],
    "unavailable_ping": [f"{emoji['unavailable']} **{{name}}** is no longer available {{available_count}} *(we still have 8 tho)*"],
    "unavailable_auto": [f"{emoji['unavailable']} **{{name}}** was marked unavailable by mods {{available_count}}"],
    "unavailable_auto_bot": [f"{emoji['unavailable']} **{{name}}** was marked unavailable automatically (no activity in past 1.5 hrs) {{available_count}}"],

    "join_vc": [f"{emoji['join_vc']} **{{member}}** joined the first voice channel {{count}}"],
    "leave_vc": [f"{emoji['leave_vc']} **{{member}}** left the first voice channel {{count}}"],
    "join_vc_2": [f"{emoji['join_vc_2']} **{{member}}** joined the second voice channel {{count}}"],
    "leave_vc_2": [f"{emoji['leave_vc']} **{{member}}** left the second voice channel {{count}}"],
    "join_vc_3": [f"{emoji['join_vc_3']} **{{member}}** joined the third voice channel {{count}}"],
    "leave_vc_3": [f"{emoji['leave_vc']} **{{member}}** left the third voice channel {{count}}"],

    "join_vc_force": [f"{emoji['join_vc']} fixed **{{member}}**'s vc roles: joined the first voice channel {{count}}"],
    "leave_vc_force": [f"{emoji['leave_vc']} fixed **{{member}}**'s vc roles: left the first voice channel {{count}}"],
    "join_vc_2_force": [f"{emoji['join_vc_2']} fixed **{{member}}**'s vc roles: joined the second voice channel {{count}}"],
    "leave_vc_2_force": [f"{emoji['leave_vc']} fixed **{{member}}**'s vc roles: left the second voice channel {{count}}"],
    "join_vc_3_force": [f"{emoji['join_vc_3']} fixed **{{member}}**'s vc roles: joined the third voice channel {{count}}"],
    "leave_vc_3_force": [f"{emoji['leave_vc']} fixed **{{member}}**'s vc roles: left the third voice channel {{count}}"],

    "edit_vc": [f"{emoji['edit_g']} **{{member}}** set the first voice channel's status to **{{status}}**"],
    "edit_vc_no_status": [f"{emoji['edit_g']} **{{member}}** changed the first voice channel's status"],
    "edit_vc_clear": [f"{emoji['edit_g']} **{{member}}** cleared the first voice channel's status"],
    "edit_vc_2": [f"{emoji['edit_p']} **{{member}}** set the second voice channel's status to **{{status}}**"],
    "edit_vc_2_no_status": [f"{emoji['edit_p']} **{{member}}** changed the second voice channel's status"],
    "edit_vc_2_clear": [f"{emoji['edit_p']} **{{member}}** cleared the second voice channel's status"],
    "edit_vc_3": [f"{emoji['edit_r']} **{{member}}** set the third voice channel's status to **{{status}}**"],
    "edit_vc_3_no_status": [f"{emoji['edit_r']} **{{member}}** changed the third voice channel's status"],
    "edit_vc_3_clear": [f"{emoji['edit_r']} **{{member}}** cleared the third voice channel's status"],

    "promotion": [
        f"{emoji['promotion']} {{mention}} is now a moderator!"
    ],
    "demotion": [
        f"{emoji['demotion']} {{mention}} was demoted..."
    ],
    "new_leader": [
        f"{emoji['promotion']} {{mention}} is now a leader!"
    ],
    "leader_removed": [
        f"{emoji['demotion']} {{mention}} is no longer a leader..."
    ],
    "promotion_welcome": [
        f"{emoji['promotion']} welcome, {{mention}}. hope this chat is cozy!"
    ],
    "demotion_goodbye": [
        f"{emoji['demotion']} {{mention}} wasn't worthy of being a mod, it seems. well, off you go"
    ],
    "name_change": [
        f"{emoji['edit']} {{mention}}'s name was changed from **{{old_name}}** to **{{new_name}}**"
    ],
    "birthday": [
        f"{emoji['birthday']} happy birthday, {{mention}}!!"
    ],
    "newbie": [
        f"{emoji['newbie']} {{mention}} is not a newbie anymore!! please applaud!!"
    ],
    "inactive": [
        f"{emoji['inactive']} {{mention}} didn't send a single message in chat in the past 6 days so marked inactive automatically"
    ],
    "inactive_mods": [
        f"{emoji['inactive']} mods marked {{mention}} inactive"
    ],
    "inactive_revoke": [
        f"{emoji['inactive_revoke']} {{mention}} is no longer considered inactive!"
    ],
    "explained_inactive": [
        f"{emoji['explained_inactive']} {{mention}}'s inactivity was excused"
    ],
    "nuh_uh": [
        "https://cdn.discordapp.com/attachments/715528165132599337/1442162843452440777/nuh-uh-3d-thumbnail-url-7g84og.png?ex=69246e4f&is=69231ccf&hm=b1bf1bb44ee89017d8404d35a1b0812eef3c6dc29a870ef3a8fefaa96fc7353e&",
    ],
    "bot_doesnt_have_perms": [
        "https://cdn.discordapp.com/attachments/715528165132599337/1442288380766457977/artworks-000519533403-ovb003-t1080x1080.png?ex=6924e33a&is=692391ba&hm=1ce891ca81be59241658390d96198e442226d78d4b4c7e708a28f5355f6ac5bb&"
    ],
    "wip": [
        "https://media.discordapp.net/attachments/715528165132599337/1450116115190513795/pug-dog-constructor-safety-helmet-yellow-black-work-progress-sign-wooden-pole-isolated-white-background-92995840.png?ex=69415d5f&is=69400bdf&hm=95a383c0b59ff99f483df65c5ab5d0b44e8628c786b847e75246b557447eb0fb&=&format=webp&quality=lossless"
    ],
    "channel_lock": [
        "🔒 channel was locked"
    ],
    "channel_unlock": [
        "🔓 channel was unlocked"
    ],
    "rp_kill": [f"{emoji['knife']} {{author}} brutally murdered {{target}}"],
    "rp_hug": [f"{emoji['hug']} {{author}} hugged {{target}}"],
    "rp_kiss": [f"{emoji['kiss']} {{author}} kissed {{target}}"],
    "rp_high_five": [f"{emoji['high_five']} {{author}} gave a high five to {{target}}"],
    "rp_handshake": [f"{emoji['handshake']} {{author}} shook hands with {{target}}"],
    "rp_burn": [f"{emoji['fire']} {{author}} set {{target}} on fire"],
    "rp_punch": [f"{emoji['punch']} {{author}} punched {{target}}"],
    "rp_slap": [f"{emoji['slap']} {{author}} slapped {{target}}"],
    "rp_pat": [f"{emoji['pat']} {{author}} patted {{target}} on the head"],
    "rp_touch": [f"{emoji['touch']} {{author}} touched {{target}}"],
}

def message(dict_key: str, **kwargs) -> str:
    import random
    res = random.choice(_messages[dict_key])
    res = res.format(**kwargs)
    return res