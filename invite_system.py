"""
Invite & Earn  (shared logic, used by commands.py /start, plugins/invite.py and the admin panel)

How it works
  * every user has a personal link  https://t.me/<bot>?start=reff_<user_id>
  * when a BRAND-NEW user opens the bot with that link, the inviter gets points
  * enough points  ->  free premium days (all numbers are editable in /panel -> Invites)
  * one person can only be counted once, you cannot invite yourself,
    and old users cannot be "re-invited"
"""
import asyncio
import datetime
import logging
import os
from urllib.parse import quote

from pyrogram import enums
from pyrogram.types import InlineKeyboardButton as Btn, InlineKeyboardMarkup as Kb
from pymongo.errors import DuplicateKeyError

from database.refer import referdb
from database.users_chats_db import db
from info import ADMINS, PREMIUM_LOGS

logger = logging.getLogger(__name__)
HTML = enums.ParseMode.HTML
_index_ready = False

# Reward settings (change them with environment variables on Render if you want)
INVITE_POINTS = int(os.environ.get("INVITE_POINTS", "10"))    # points for each new friend
INVITE_TARGET = int(os.environ.get("INVITE_TARGET", "100"))   # points needed for the reward
INVITE_DAYS = int(os.environ.get("INVITE_DAYS", "30"))        # free premium days as reward


def _col():
    return db.db.referrals


async def _ensure_index():
    global _index_ready
    if _index_ready:
        return
    try:
        await _col().create_index("new_user", unique=True)
        await _col().create_index("referrer")
        _index_ready = True
    except Exception:
        logger.exception("referrals index creation failed")


def link_for(bot_username: str, user_id: int) -> str:
    return f"https://t.me/{bot_username}?start=reff_{user_id}"


def _bar(done: int, total: int, width: int = 10) -> str:
    total = max(total, 1)
    filled = max(0, min(width, int(width * done / total)))
    return "🟩" * filled + "⬜" * (width - filled)


async def invited_count(user_id: int) -> int:
    await _ensure_index()
    return await _col().count_documents({"referrer": int(user_id)})


async def total_invites() -> int:
    await _ensure_index()
    return await _col().count_documents({})


async def top_inviters(limit: int = 10):
    await _ensure_index()
    cur = _col().aggregate([
        {"$group": {"_id": "$referrer", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
        {"$limit": limit},
    ])
    return [(d["_id"], d["n"]) async for d in cur]


async def _name_of(uid: int) -> str:
    doc = await db.col.find_one({"id": int(uid)}, {"name": 1})
    return ((doc or {}).get("name") or "User")[:18]


async def _points(uid: int) -> int:
    return await asyncio.to_thread(referdb.get_refer_points, int(uid))


async def _set_points(uid: int, pts: int):
    await asyncio.to_thread(referdb.add_refer_points, int(uid), int(pts))


# --------------------------------------------------------------------------- #
# Registering an invite (called from /start reff_<id>)                         #
# --------------------------------------------------------------------------- #
async def register_invite(client, message, referrer_id: int, is_new_user: bool):
    """Returns nothing; talks to the user itself."""
    me = message.from_user

    if referrer_id == me.id:
        return await message.reply_text(
            "<b>😄 ʏᴏᴜ ᴄᴀɴ'ᴛ ɪɴᴠɪᴛᴇ ʏᴏᴜʀsᴇʟꜰ!</b>\n\n"
            "ꜱʜᴀʀᴇ ʏᴏᴜʀ ʟɪɴᴋ ᴡɪᴛʜ ꜰʀɪᴇɴᴅꜱ ᴀɴᴅ ᴇᴀʀɴ ᴘᴏɪɴᴛꜱ 👉 /refer", parse_mode=HTML)

    if not is_new_user:
        return await message.reply_text(
            "<b>ℹ️ ʏᴏᴜ ᴀʟʀᴇᴀᴅʏ ᴜsᴇ ᴛʜɪs ʙᴏᴛ.</b>\n<i>Invite links count only for brand-new users.</i>",
            parse_mode=HTML)

    # the inviter must be a real, non-banned user of this bot
    if not await db.is_user_exist(referrer_id):
        return
    ban = await db.get_ban_status(referrer_id)
    if ban.get("is_banned"):
        return

    await _ensure_index()
    try:
        await _col().insert_one({
            "new_user": me.id, "referrer": referrer_id,
            "ts": datetime.datetime.utcnow(),
        })
    except DuplicateKeyError:
        return await message.reply_text("<b>ℹ️ ʏᴏᴜ ʜᴀᴠᴇ ᴀʟʀᴇᴀᴅʏ ʙᴇᴇɴ ɪɴᴠɪᴛᴇᴅ ʙᴇꜰᴏʀᴇ.</b>", parse_mode=HTML)

    per, target, days = INVITE_POINTS, INVITE_TARGET, INVITE_DAYS
    total = await _points(referrer_id) + per

    rewarded = False
    if total >= target:
        total -= target
        rewarded = True
        await _grant_premium(referrer_id, days)
    await _set_points(referrer_id, total)

    inviter_name = await _name_of(referrer_id)
    await message.reply_text(
        f"<b>🎉 ᴡᴇʟᴄᴏᴍᴇ!</b>\nʏᴏᴜ ᴡᴇʀᴇ ɪɴᴠɪᴛᴇᴅ ʙʏ <b>{inviter_name}</b> 💖\n\n"
        "ɪɴᴠɪᴛᴇ ʏᴏᴜʀ ꜰʀɪᴇɴᴅꜱ ᴛᴏᴏ ᴀɴᴅ ᴇᴀʀɴ ꜰʀᴇᴇ ᴘʀᴇᴍɪᴜᴍ 👉 /refer",
        parse_mode=HTML)

    try:
        text = (f"<b>🎉 ɴᴇᴡ ꜰʀɪᴇɴᴅ ᴊᴏɪɴᴇᴅ!</b>\n\n"
                f"{me.mention} ᴊᴏɪɴᴇᴅ ᴜsɪɴɢ ʏᴏᴜʀ ʟɪɴᴋ.\n"
                f"➕ <b>{per}</b> ᴘᴏɪɴᴛs  •  ʏᴏᴜʀ ᴘᴏɪɴᴛs: <b>{total}/{target}</b>")
        if rewarded:
            text += f"\n\n🎁 <b>ʏᴏᴜ ɢᴏᴛ {days} ᴅᴀʏs ᴘʀᴇᴍɪᴜᴍ ꜰʀᴇᴇ!</b> 👑"
        await client.send_message(referrer_id, text, parse_mode=HTML)
    except Exception:
        pass

    if rewarded:
        note = (f"<b>#Invite_Reward</b>\n\n👤 {inviter_name} (<code>{referrer_id}</code>) earned "
                f"<b>{days} days</b> premium by inviting users.")
        for admin in ADMINS:
            try:
                await client.send_message(admin, note, parse_mode=HTML)
            except Exception:
                pass
        try:
            await client.send_message(PREMIUM_LOGS, note, parse_mode=HTML)
        except Exception:
            pass


async def _grant_premium(user_id: int, days: int):
    """Add `days` of premium on top of whatever the user already has."""
    now = datetime.datetime.now()
    doc = await db.users.find_one({"id": int(user_id)}) or {}
    current = doc.get("expiry_time")
    base = current if isinstance(current, datetime.datetime) and current > now else now
    await db.update_user({"id": int(user_id), "expiry_time": base + datetime.timedelta(days=days)})


# --------------------------------------------------------------------------- #
# User-facing pages                                                            #
# --------------------------------------------------------------------------- #
async def invite_page(bot, user):
    """(text, keyboard) of the personal invite page."""
    link = link_for(bot.me.username, user.id)
    per, target, days = INVITE_POINTS, INVITE_TARGET, INVITE_DAYS
    invited = await invited_count(user.id)
    pts = await _points(user.id)
    need = max(target - pts, 0)
    friends_left = -(-need // per) if per else 0

    text = (
        "<b>🎁 ɪɴᴠɪᴛᴇ & ᴇᴀʀɴ</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━</b>\n"
        f"👥 <b>ꜰʀɪᴇɴᴅs ɪɴᴠɪᴛᴇᴅ:</b> <code>{invited}</code>\n"
        f"⭐ <b>ʏᴏᴜʀ ᴘᴏɪɴᴛs:</b> <code>{pts}/{target}</code>\n"
        f"{_bar(pts, target)}\n"
        f"🎯 <b>ɴᴇxᴛ ʀᴇᴡᴀʀᴅ ɪɴ:</b> <code>{friends_left}</code> ꜰʀɪᴇɴᴅ(s)\n"
        "<b>━━━━━━━━━━━━━━━━━━</b>\n"
        f"➕ ᴇᴀᴄʜ ɴᴇᴡ ꜰʀɪᴇɴᴅ = <b>{per}</b> ᴘᴏɪɴᴛs\n"
        f"👑 <b>{target}</b> ᴘᴏɪɴᴛs = <b>{days} ᴅᴀʏs</b> ꜰʀᴇᴇ ᴘʀᴇᴍɪᴜᴍ\n\n"
        f"🔗 <b>ʏᴏᴜʀ ʟɪɴᴋ:</b>\n<code>{link}</code>"
    )
    share_text = quote("Hello! Try this bot - a huge library of movies and series 😃")
    kb = Kb([
        [Btn("📤 sʜᴀʀᴇ ʟɪɴᴋ", url=f"https://t.me/share/url?url={quote(link)}&text={share_text}")],
        [Btn("🏆 ᴛᴏᴘ ɪɴᴠɪᴛᴇʀs", callback_data="invite_top"),
         Btn("🔄 ʀᴇꜰʀᴇsʜ", callback_data="invite_menu")],
        [Btn("⬅️ ʙᴀᴄᴋ", callback_data="start")],
    ])
    return text, kb


async def leaderboard_page():
    rows = await top_inviters(10)
    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
    if rows:
        lines = []
        for i, (uid, n) in enumerate(rows):
            lines.append(f"{medals[i]} <b>{await _name_of(uid)}</b> — <code>{n}</code>")
        body = "\n".join(lines)
    else:
        body = "<i>No invites yet — be the first! 🚀</i>"
    text = f"<b>🏆 ᴛᴏᴘ ɪɴᴠɪᴛᴇʀs</b>\n<b>━━━━━━━━━━━━━━━━━━</b>\n{body}"
    kb = Kb([[Btn("⬅️ ʙᴀᴄᴋ", callback_data="invite_menu")]])
    return text, kb


async def edit_or_reply(query, text, kb):
    """Edit the current message (text or photo-caption); fall back to a new message."""
    try:
        if query.message.photo or query.message.video or query.message.document:
            await query.message.edit_caption(text, reply_markup=kb, parse_mode=HTML)
        else:
            await query.message.edit_text(text, reply_markup=kb, parse_mode=HTML,
                                          disable_web_page_preview=True)
    except Exception as e:
        if "MESSAGE_NOT_MODIFIED" in str(e).upper():
            return
        try:
            await query.message.reply_text(text, reply_markup=kb, parse_mode=HTML,
                                           disable_web_page_preview=True)
        except Exception:
            logger.exception("invite page send failed")
