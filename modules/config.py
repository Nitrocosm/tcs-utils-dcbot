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
    ...
}

verification_messages = {
    # ── Button labels ──
    "btn_verify": "verify ({needed} more)",
    "btn_request_mod": "lock & request mod",
    "btn_change": "change challenge",
    "btn_official": "official challenge",
    "btn_custom": "custom challenge",
    "btn_joke": "joke badge",
    "btn_fail": "this is a failed or incomplete run",
    "btn_reopen": "make this a verification request",
    "btn_tab_official": "official challenge",
    "btn_tab_custom": "custom challenge",
    "btn_tab_joke": "joke badge",
    "btn_no_footage": "no footage / other platform",
    "btn_verify_anyway": "yes, verify anyway",
    "btn_verify_self": "yes, i'm sure, verify anyway",
    "btn_cancel": "cancel",
    "btn_escalate": "yes, escalate",
    "btn_resolve": "resolve report",
    "btn_manual_enter": "enter manual mode",
    "btn_manual_exit": "exit manual mode",
    "btn_manual_verify_no_roles": "mark verified & don't give roles",
    "btn_manual_verify_roles": "mark verified as usual",
    "select_placeholder": "select a challenge...",
    "no_challenges": "no challenges available",
    "btn_prev": "< prev",
    "btn_next": "next >",

    # ── Main bot message (pinned) ──
    "msg_header_title": "# <:doors_clock:1499578504000311386> {role_mention} completion",
    "msg_header_body": "{op_mention} completed **{name}**",
    "msg_body_reported": "## <:disconnect:1499465485144686682> reported - awaiting moderator review",
    "msg_body_manual": "## <:required:1463357222632292458> manual mode - only moderators can act",
    "msg_body_ready": "## <:yes:1463357188964618413> video is ready // {done}/{needed} verifications",
    "msg_body_ready_last": "-# last verifier: {last}",
    "msg_body_uploading": "## <:doors_globe:1499578536904622101> the video is uploading",
    "msg_body_uploading_check": "-# will ping the verifiers when the video is ready\n-# next check: <t:{ts}:R>",
    "msg_body_uploading_hint": "",
    "msg_body_no_video": "## <:not_applicable:1500106312560672912> waiting for a youtube link\n-# send a link! make sure the video isn't private and is either unlisted or public",
    "msg_body_no_footage": "## <:no:1454950318042255410> no footage or other platform",
    "msg_body_no_video_hint": "edit your post or paste a youtube link in this chat",
    "msg_url_line": "-# {url}",

    # ── Flow messages ──
    "flow_start": "# <@{op_id}>, what challenge did you complete?\nselect a category below",
    "flow_pick_category": "# {op_mention}, what challenge did you complete?\nselect a category below",
    "flow_pick_challenge": "# pick a challenge\nuse the dropdown to select the one you completed",
    "flow_ignore": "# <:disconnect:1499465485144686682> this thread is marked as incomplete or failed\nthe runner stated this is a failed or incomplete run.\nif this changes, click the button below to turn it back into a verification request.",
    "flow_ask_video": "<@{op_id}> **the bot only supports youtube links.**\nedit your original post to add one, or paste a link in this chat.\n***by the way, you can send the link even before it's finished uploading! the bot will ping the verifiers when it's watchable automatically.***\nif you don't have footage or are using another platform, click below to skip the youtube requirement.",
    "flow_manual_desc": "\n\n<:required:1463357222632292458> **manual mode** - only moderators can interact with the buttons below. use them to resolve this thread.",

    # ── Verification event messages ──
    "verif_ping": "## <:required:1463357222632292458> <@&{VERIFIER_ROLE_ID}> new **{name}** completion!\n-# after watching the video click \"verify\" on the pinned message above\n-# if something needs a moderator, click \"request mod\" instead\n-# make sure the correct challenge is selected",
    "verif_in_progress": "<:yes:1463357188964618413> verified by {mention} // {remaining} more needed",
    "verif_complete": "<:yes:1463357188964618413> verified by {mention} // run is verified!",
    "verif_done_bot": "# <:doors_trophy:1499481077272674456> verified {role_mention} completion",
    "verif_done_thread": "<:doors_trophy:1499481077272674456> {role_mention} finished verification!\n-# the role was given automatically\n-# the bot doesn't do <#1427066908812906526> posts yet, if one needs to be done - do it",

    # ── Owner override / verification prompts ──
    "prompt_self_verify_owner": "you're the runner of this run **and** the server owner.\nare you sure you want to verify yourself?",
    "prompt_redo_owner": "you already verified this run. are you sure you want to do it again?",
    "prompt_owner_no_role": "you don't have the verifier role. are you sure you want to verify this run?",

    # ── Ephemeral error / info messages ──
    "err_not_verifier": "you don't have permission to do that",
    "err_not_op": "this isn't for you",
    "err_no_identity": "could not verify identity",
    "err_locked": "this thread is locked for verification",
    "err_self_verify": "you can't verify your own run",
    "err_already_done": "you already verified this run",
    "err_cant_change": "can't change challenge after a verification has happened",
    "err_no_bot_msg": "could not find the verification message",
    "info_proceeding": "proceeding...",
    "info_cancelled": "verification cancelled",
    "err_role_not_found": "role not found",
    "err_invalid_challenge": "invalid challenge",
    "err_rejected": "this run has been rejected and can no longer be verified",

    # ── Report flow ──
    "report_prompt": "# request moderation assistance\nthis will pause verifications and ping <@&{MOD_ROLE_ID}>.\na moderator will review the thread and decide what to do.\n\n**this doesn't mean the run is invalid or cheated.** it just means a human needs to look at it \u2014 for example:\n\u2022 the bot can't handle what's needed (e.g. awarding multiple roles)\n\u2022 the runner picked the wrong challenge and can't change it\n\u2022 anything else that requires assistance\n### are you sure you want to escalate?",
    "report_escalated": "# run escalated to moderators",
    "report_notify": "<:restricted:1500105022166536292> <@&{MOD_ROLE_ID}> this needs mod assistance",
    "report_cancelled": "report cancelled",
    "report_resolved": "<:yes:1463357188964618413> {mention} resolved the report",

    # ── Manual mode ──
    "manual_activated": "<:doors_lock:1499468754378297645> {mention} activated manual mode",
    "manual_exit": "{mention} ended manual mode",
    "manual_verify_no_roles": "<:doors_trophy:1499481077272674456> {role_mention} was marked as verified without awarding roles\n-# by {mention}",
    "manual_verify_roles": "<:doors_trophy:1499481077272674456> {role_mention} verified by {mention}\n-# the role was given automatically",

    # ── Reject flow ──
    "btn_reject": "reject run",
    "btn_reinstate": "reinstate",
    "reject_prompt": "# reject this run?\nthis will stop verifications and mark it as rejected.\na moderator will need to reinstate it before it can continue.\n### are you sure?",
    "reject_cancelled": "rejection cancelled",
    "reject_notify": "<:death:1454943637904425141> {mention} rejected this run",
    "rejected_resolved": "<:doors_clock:1499578504000311386> {mention} reinstated the run",
    "msg_body_rejected": "## <:no:1454950318042255410> run rejected",

    # ── Verification completion ──
    "msg_body_verified_by": "verified by {verifiers}",
}

def message(dict_key: str, **kwargs) -> str:
    import random
    res = random.choice(_messages[dict_key])
    res = res.format(**kwargs)
    return res