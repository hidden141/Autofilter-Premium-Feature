"""
👑 ADMIN PANEL  +  📨 CONTACT-ADMIN SUPPORT INBOX
=================================================

ADMIN (private chat, ADMINS only)
  /panel  (/admin)        colourful control panel with live stats
  /userinfo <id|reply>    full user card + quick actions (ban, premium, reply)
  /tickets                open support inbox
  /maintenance on|off     quick maintenance switch
  /cancel                 cancel a pending reply / broadcast compose

USER (any private chat)
  /contact  (/support)    talk to the admin through the bot

How user -> admin works
  * The user taps "Contact Admin" (or sends /contact) and writes anything
    (text, photo, video, document, voice ...).
  * Every message reaches ALL admins with a small header + buttons
    [Reply] [Info] [Close] [Ban].
  * Admin answers by swipe-replying to the message, or by tapping [Reply]
    and sending the next message. Replies are delivered to the user with an
    [Reply] button so the conversation can continue.
  * Tickets and message->user routing are stored in MongoDB, so replies keep
    working after a restart / Render redeploy.

Everything lives in this one file; remove it to remove the feature.
"""
import asyncio
import datetime
import html
import io
import logging
import os
import platform
import sys
import time

import psutil
import pytz
from pymongo import ReturnDocument
from pyrogram import Client, filters, enums, __version__ as PYRO_VERSION
from pyrogram.errors import (
    FloodWait, MessageNotModified, UserIsBlocked, InputUserDeactivated, PeerIdInvalid
)
from pyrogram.types import InlineKeyboardButton as B, InlineKeyboardMarkup as KB

from info import ADMINS, MULTIPLE_DB
from database.users_chats_db import db
from database.ia_filterdb import Media, Media2, db as media_db, db2 as media_db2
from utils import temp, get_size, get_readable_time

logger = logging.getLogger(__name__)

HTML = enums.ParseMode.HTML
IST = pytz.timezone("Asia/Kolkata")
START_TIME = time.time()

CONTACT_TTL = 600            # seconds of inactivity before contact mode ends
FLOOD_MAX, FLOOD_WINDOW = 6, 60   # max messages per window from one user
REPLY_TTL = 600              # seconds a pending "[Reply]" stays armed
SEND_ERRORS = (UserIsBlocked, InputUserDeactivated, PeerIdInvalid)
ADMIN_IDS = [a for a in ADMINS if isinstance(a, int)]

TICKETS = db.db.tickets
TMAP = db.db.ticket_map
COUNTERS = db.db.counters

# ---------------------------------------------------------------- state ----
CONTACT = {}      # user_id  -> last activity timestamp (contact mode)
FLOOD = {}        # user_id  -> [timestamps]
REPLYING = {}     # admin_id -> (user_id, ticket_id, ts)
COMPOSE = {}      # admin_id -> ts   (waiting for a broadcast message)
PENDING_BC = {}   # admin_id -> Message to broadcast (waiting for confirm)
_FLAGS = {}       # key -> (value, ts)  tiny cache for bot settings
_bc_lock = asyncio.Lock()
BC = {"cancel": False}
_index_done = False

LAST_SEEN = {}    # user_id -> last activity timestamp (this process)
_PERSIST = {}     # user_id -> last time last_seen was written to MongoDB
ONLINE_WINDOW = 300          # "online" = active in the last 5 minutes


# ------------------------------------------------------------- helpers -----
def esc(s) -> str:
    return html.escape(str(s or ""))


def is_admin(uid) -> bool:
    return uid in ADMINS


def now_ist() -> str:
    return datetime.datetime.now(IST).strftime("%d %b %Y • %I:%M %p")


def bar(pct: float, size: int = 10) -> str:
    """Clean monochrome progress bar without coloured square emojis."""
    pct = max(0.0, min(100.0, float(pct)))
    filled = round(pct / 100 * size)
    return "▰" * filled + "▱" * (size - filled)


def on_off(v) -> str:
    return "🟢 ᴏɴ" if v else "⚪ ᴏꜰꜰ"


async def get_flag(key, default):
    cached = _FLAGS.get(key)
    if cached and time.time() - cached[1] < 30:
        return cached[0]
    try:
        val = await db.get_bot_setting(temp.ME, key, default)
    except Exception:
        logger.exception("get_flag(%s) failed", key)
        val = default
    _FLAGS[key] = (val, time.time())
    return val


async def set_flag(key, value):
    await db.update_bot_setting(temp.ME, key, value)
    _FLAGS[key] = (value, time.time())


async def safe_count(coro):
    try:
        return await coro
    except Exception:
        logger.exception("count failed")
        return 0


async def ensure_indexes():
    global _index_done
    if _index_done:
        return
    _index_done = True
    try:
        await TMAP.create_index([("admin", 1), ("mid", 1)])
        await TMAP.create_index("at", expireAfterSeconds=60 * 60 * 24 * 30)
        await TICKETS.create_index([("uid", 1), ("status", 1)])
    except Exception:
        logger.exception("ticket index creation failed")


async def show(query, text, kb):
    """Edit the panel message in place (or send a fresh one when the source
    message is a photo, e.g. the /start menu)."""
    try:
        if query.message.photo or query.message.video or query.message.document:
            await query.message.reply_text(text, reply_markup=kb, parse_mode=HTML,
                                           disable_web_page_preview=True)
        else:
            await query.message.edit_text(text, reply_markup=kb, parse_mode=HTML,
                                          disable_web_page_preview=True)
    except MessageNotModified:
        pass


def _auto_delete(msg, seconds):
    async def _job():
        await asyncio.sleep(seconds)
        try:
            await msg.delete()
        except Exception:
            pass
    asyncio.create_task(_job())


# ------------------------------------------------------------- tickets -----
async def next_ticket_id() -> int:
    doc = await COUNTERS.find_one_and_update(
        {"_id": "tickets"}, {"$inc": {"n": 1}},
        upsert=True, return_document=ReturnDocument.AFTER)
    return int(doc["n"])


async def get_or_create_ticket(user):
    t = await TICKETS.find_one({"uid": user.id, "status": "open"})
    if t:
        return t, False
    t = {
        "_id": await next_ticket_id(), "uid": user.id,
        "name": user.first_name or "User", "uname": user.username or "",
        "status": "open", "count": 0,
        "created": datetime.datetime.utcnow(), "updated": datetime.datetime.utcnow(),
    }
    await TICKETS.insert_one(t)
    return t, True


def ticket_kb(tid, uid, closed=False):
    first = B("🔓 ʀᴇᴏᴘᴇɴ", callback_data=f"tk:open:{tid}") if closed else \
        B("✅ ᴄʟᴏꜱᴇ", callback_data=f"tk:close:{tid}")
    return KB([
        [B("💬 ʀᴇᴘʟʏ", callback_data=f"tk:reply:{tid}"),
         B("👤 ɪɴꜰᴏ", callback_data=f"ap:ui:{uid}")],
        [first, B("⛔ ʙᴀɴ", callback_data=f"ap:ban:{uid}")],
    ])


async def remember(admin_id, mid, uid, tid):
    try:
        await TMAP.insert_one({"admin": admin_id, "mid": mid, "uid": uid, "tid": tid,
                               "at": datetime.datetime.utcnow()})
    except Exception:
        logger.exception("ticket map insert failed")


async def deliver_to_user(bot, message, uid, tid) -> bool:
    """Send an admin message to the user (text gets a styled header)."""
    kb = KB([[B("✍️ ʀᴇᴘʟʏ ᴛᴏ ᴀᴅᴍɪɴ", callback_data="ct:start")]])
    head = f"<b>📩 ʀᴇᴘʟʏ ꜰʀᴏᴍ ᴀᴅᴍɪɴ</b>  •  <code>#{tid}</code>"
    try:
        try:
            if message.text:
                await bot.send_message(uid, f"{head}\n\n{message.text.html}",
                                       reply_markup=kb, parse_mode=HTML)
            else:
                await bot.send_message(uid, head, parse_mode=HTML)
                await message.copy(uid, reply_markup=kb)
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
            return await deliver_to_user(bot, message, uid, tid)
    except SEND_ERRORS:
        return False
    except Exception:
        logger.exception("deliver_to_user failed")
        return False
    await TICKETS.update_one({"_id": tid}, {"$set": {"status": "open",
                                                    "updated": datetime.datetime.utcnow()}})
    return True


# ------------------------------------------------------ activity tracker ---
async def _persist_seen(uid):
    try:
        await db.col.update_one({"id": uid}, {"$set": {"last_seen": datetime.datetime.utcnow()}})
    except Exception:
        logger.debug("last_seen write failed", exc_info=True)


def touch(uid):
    now = time.time()
    LAST_SEEN[uid] = now
    if len(LAST_SEEN) > 50000:   # keep memory bounded
        for k in [k for k, t in LAST_SEEN.items() if now - t > 3600]:
            LAST_SEEN.pop(k, None)
    if now - _PERSIST.get(uid, 0) > 120:
        _PERSIST[uid] = now
        asyncio.create_task(_persist_seen(uid))


@Client.on_message(filters.incoming, group=-10)
async def track_message_activity(bot, message):
    if message.from_user:
        touch(message.from_user.id)


@Client.on_callback_query(group=-10)
async def track_callback_activity(bot, query):
    if query.from_user:
        touch(query.from_user.id)


def online_now() -> int:
    cutoff = time.time() - ONLINE_WINDOW
    return sum(1 for t in LAST_SEEN.values() if t > cutoff)


async def active_since(seconds: int) -> int:
    since = datetime.datetime.utcnow() - datetime.timedelta(seconds=seconds)
    return await safe_count(db.col.count_documents({"last_seen": {"$gt": since}}))


async def storage_lines():
    """Database storage usage (same 512 MB free-tier assumption as /stats)."""
    limit = 512 * 1024 * 1024
    out = []
    for label, mdb in (("ᴅʙ 1", media_db), ("ᴅʙ 2", media_db2 if MULTIPLE_DB else None)):
        if mdb is None:
            continue
        try:
            st = await mdb.command("dbStats")
            used = st["dataSize"] + st["indexSize"]
            out.append(f"💾 {label} {bar(used / limit * 100)} <code>{get_size(used)}</code>")
        except Exception:
            logger.debug("dbStats failed", exc_info=True)
    return out


async def total_files() -> int:
    n = await safe_count(Media.count_documents())
    if MULTIPLE_DB:
        n += await safe_count(Media2.count_documents())
    return n


# ------------------------------------------------------- admin panel UI ----
async def home_text():
    users = await safe_count(db.total_users_count())
    prem = await safe_count(db.all_premium_users())
    open_t = await safe_count(TICKETS.count_documents({"status": "open"}))
    return (
        "<b>╔══════════════════╗\n"
        "   👑  ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ  👑\n"
        "╚══════════════════╝</b>\n\n"
        f"👥 <b>ᴜꜱᴇʀꜱ</b> : <code>{users}</code>\n"
        f"⚡ <b>ᴏɴʟɪɴᴇ ɴᴏᴡ</b> : <code>{online_now()}</code>\n"
        f"💎 <b>ᴘʀᴇᴍɪᴜᴍ</b> : <code>{prem}</code>\n"
        f"📨 <b>ᴏᴘᴇɴ ᴛɪᴄᴋᴇᴛꜱ</b> : <code>{open_t}</code>\n"
        f"⏱ <b>ᴜᴘᴛɪᴍᴇ</b> : <code>{get_readable_time(time.time() - START_TIME)}</code>\n\n"
        "<i>👇 ᴄʜᴏᴏꜱᴇ ᴀ ꜱᴇᴄᴛɪᴏɴ</i>"
    )


async def home_kb():
    open_t = await safe_count(TICKETS.count_documents({"status": "open"}))
    badge = f" ({open_t})" if open_t else ""
    return KB([
        [B("📊 ᴅᴀꜱʜʙᴏᴀʀᴅ", callback_data="ap:dash"), B("👥 ᴜꜱᴇʀꜱ", callback_data="ap:users")],
        [B("💎 ᴘʀᴇᴍɪᴜᴍ", callback_data="ap:prem"), B("📢 ʙʀᴏᴀᴅᴄᴀꜱᴛ", callback_data="ap:bc")],
        [B("⛔ ʙᴀɴꜱ", callback_data="ap:bans"), B("⚙️ ꜱᴇᴛᴛɪɴɢꜱ", callback_data="ap:set")],
        [B(f"📨 ɪɴʙᴏx{badge}", callback_data="ap:inbox"), B("💻 ꜱʏꜱᴛᴇᴍ", callback_data="ap:sys")],
        [B("📚 ᴄᴏᴍᴍᴀɴᴅꜱ", callback_data="ap:cmds"), B("✖️ ᴄʟᴏꜱᴇ", callback_data="ap:close")],
    ])


BACK = [B("⬅️ ʙᴀᴄᴋ", callback_data="ap:home")]


async def dash_text():
    users = await safe_count(db.total_users_count())
    chats = await safe_count(db.total_chat_count())
    prem = await safe_count(db.all_premium_users())
    files = await total_files()
    open_t = await safe_count(TICKETS.count_documents({"status": "open"}))
    closed_t = await safe_count(TICKETS.count_documents({"status": "closed"}))
    d1, d7 = await active_since(86400), await active_since(7 * 86400)
    cpu, ram = psutil.cpu_percent(), psutil.virtual_memory().percent
    storage = "\n".join(await storage_lines())
    return (
        "<b>📊 ᴅᴀꜱʜʙᴏᴀʀᴅ</b>\n━━━━━━━━━━━━━━━━━━\n"
        f"👥 ᴛᴏᴛᴀʟ ᴜꜱᴇʀꜱ : <code>{users}</code>\n"
        f"⚡ ᴏɴʟɪɴᴇ ɴᴏᴡ : <code>{online_now()}</code>  <i>(5 ᴍɪɴ)</i>\n"
        f"📅 ᴀᴄᴛɪᴠᴇ 24ʜ : <code>{d1}</code>  •  7ᴅ : <code>{d7}</code>\n"
        f"💎 ᴘʀᴇᴍɪᴜᴍ : <code>{prem}</code>\n"
        f"⛔ ʙᴀɴɴᴇᴅ ᴜꜱᴇʀꜱ : <code>{len(temp.BANNED_USERS)}</code>\n"
        f"💬 ɢʀᴏᴜᴘꜱ : <code>{chats}</code>  •  ᴅɪꜱᴀʙʟᴇᴅ : <code>{len(temp.BANNED_CHATS)}</code>\n"
        f"🎬 ꜰɪʟᴇꜱ : <code>{files}</code>\n"
        f"📨 ᴛɪᴄᴋᴇᴛꜱ : <code>{open_t}</code> ᴏᴘᴇɴ / <code>{closed_t}</code> ᴄʟᴏꜱᴇᴅ\n\n"
        + (storage + "\n" if storage else "")
        + f"⚙️ ᴄᴘᴜ  {bar(cpu)} <code>{cpu:.0f}%</code>\n"
        f"🧠 ʀᴀᴍ  {bar(ram)} <code>{ram:.0f}%</code>\n"
        f"⏱ ᴜᴘᴛɪᴍᴇ : <code>{get_readable_time(time.time() - START_TIME)}</code>\n"
        f"🕒 {now_ist()}\n\n"
        "<i>ᴏɴʟɪɴᴇ / ᴀᴄᴛɪᴠᴇ ᴄᴏᴜɴᴛꜱ ꜱᴛᴀʀᴛ ꜰʀᴏᴍ ᴛʜᴇ ᴍᴏᴍᴇɴᴛ ᴛʜɪꜱ ᴜᴘᴅᴀᴛᴇ ɢᴏᴇꜱ ʟɪᴠᴇ.</i>"
    )


def sys_text():
    vm, disk = psutil.virtual_memory(), psutil.disk_usage("/")
    cpu = psutil.cpu_percent()
    return (
        "<b>🖥 ꜱʏꜱᴛᴇᴍ</b>\n━━━━━━━━━━━━━━━━━━\n"
        f"⚙️ ᴄᴘᴜ   {bar(cpu)} <code>{cpu:.0f}%</code>\n"
        f"🧠 ʀᴀᴍ   {bar(vm.percent)} <code>{get_size(vm.used)} / {get_size(vm.total)}</code>\n"
        f"💾 ᴅɪꜱᴋ  {bar(disk.percent)} <code>{get_size(disk.used)} / {get_size(disk.total)}</code>\n\n"
        f"🐍 ᴘʏᴛʜᴏɴ : <code>{platform.python_version()}</code>\n"
        f"📡 ᴘʏʀᴏɢʀᴀᴍ : <code>{PYRO_VERSION}</code>\n"
        f"🧩 ᴏꜱ : <code>{platform.system()} {platform.release()}</code>\n"
        f"⏱ ᴜᴘᴛɪᴍᴇ : <code>{get_readable_time(time.time() - START_TIME)}</code>"
    )


CMD_CATS = {
    "usr": ("👥 ᴜꜱᴇʀꜱ", [
        ("/users", "ʟɪꜱᴛ ᴀʟʟ ᴜꜱᴇʀꜱ"),
        ("/userinfo <id>", "ᴜꜱᴇʀ ᴄᴀʀᴅ ᴡɪᴛʜ ᴀᴄᴛɪᴏɴꜱ"),
        ("/ban <id> [reason]", "ʙᴀɴ ᴀ ᴜꜱᴇʀ"),
        ("/unban <id>", "ᴜɴʙᴀɴ ᴀ ᴜꜱᴇʀ"),
        ("/chat <id>", "ʟɪᴠᴇ ᴄʜᴀᴛ ᴡɪᴛʜ ᴀ ᴜꜱᴇʀ"),
        ("/endchat", "ᴇɴᴅ ʟɪᴠᴇ ᴄʜᴀᴛ"),
        ("/msg <id> <text>", "ꜱᴇɴᴅ ᴏɴᴇ ᴍᴇꜱꜱᴀɢᴇ ᴛᴏ ᴀ ᴜꜱᴇʀ"),
        ("/send", "ꜱᴇɴᴅ ᴀ ʀᴇᴘʟɪᴇᴅ ᴍᴇꜱꜱᴀɢᴇ ᴛᴏ ᴀ ᴜꜱᴇʀ"),
        ("/delreq", "ᴄʟᴇᴀʀ ꜱᴀᴠᴇᴅ ᴊᴏɪɴ ʀᴇǫᴜᴇꜱᴛꜱ"),
    ]),
    "prem": ("💎 ᴘʀᴇᴍɪᴜᴍ", [
        ("/add_premium <id> 1 month", "ɢɪᴠᴇ ᴘʀᴇᴍɪᴜᴍ"),
        ("/remove_premium <id>", "ʀᴇᴍᴏᴠᴇ ᴘʀᴇᴍɪᴜᴍ"),
        ("/premium_users", "ʟɪꜱᴛ ᴘʀᴇᴍɪᴜᴍ ᴜꜱᴇʀꜱ"),
        ("/get_premium <id>", "ᴘʀᴇᴍɪᴜᴍ ɪɴꜰᴏ ᴏꜰ ᴀ ᴜꜱᴇʀ"),
        ("/trial_reset [id]", "ʀᴇꜱᴇᴛ ꜰʀᴇᴇ ᴛʀɪᴀʟ"),
        ("/plan  ·  /myplan", "ᴘʟᴀɴꜱ / ᴍʏ ᴘʟᴀɴ (ᴀʟʟ ᴜꜱᴇʀꜱ)"),
    ]),
    "bc": ("📢 ʙʀᴏᴀᴅᴄᴀꜱᴛ", [
        ("/broadcast (reply)", "ʙʀᴏᴀᴅᴄᴀꜱᴛ ᴛᴏ ᴀʟʟ ᴜꜱᴇʀꜱ"),
        ("/grp_broadcast (reply)", "ʙʀᴏᴀᴅᴄᴀꜱᴛ ᴛᴏ ᴀʟʟ ɢʀᴏᴜᴘꜱ"),
        ("/msg all <text>", "ꜱᴇɴᴅ ᴛᴇxᴛ ᴛᴏ ᴇᴠᴇʀʏᴏɴᴇ"),
        ("/clear_junk", "ʀᴇᴍᴏᴠᴇ ᴅᴇᴀᴅ ᴜꜱᴇʀꜱ"),
        ("/junk_group", "ʀᴇᴍᴏᴠᴇ ᴅᴇᴀᴅ ɢʀᴏᴜᴘꜱ"),
    ]),
    "files": ("🎬 ꜰɪʟᴇꜱ / ᴅʙ", [
        ("/delete <name>", "ᴅᴇʟᴇᴛᴇ ᴀ ꜰɪʟᴇ ꜰʀᴏᴍ ᴅʙ"),
        ("/deleteall", "ᴅᴇʟᴇᴛᴇ ᴀʟʟ ꜰɪʟᴇꜱ"),
        ("/deletefiles <keyword>", "ᴅᴇʟᴇᴛᴇ ꜰɪʟᴇꜱ ʙʏ ᴋᴇʏᴡᴏʀᴅ"),
        ("/setskip <number>", "ꜱᴇᴛ ɪɴᴅᴇx ꜱᴋɪᴘ ɴᴜᴍʙᴇʀ"),
        ("/del_msg", "ᴄʟᴇᴀʀ ɴᴏᴛɪꜰɪᴄᴀᴛɪᴏɴ ꜰɪʟᴇɴᴀᴍᴇꜱ"),
        ("/movie_update on|off", "ᴍᴏᴠɪᴇ ᴜᴘᴅᴀᴛᴇ ɴᴏᴛɪꜰʏ"),
        ("/pm_search on|off", "ᴘᴍ ꜱᴇᴀʀᴄʜ"),
    ]),
    "grp": ("🏘 ɢʀᴏᴜᴘꜱ", [
        ("/chats", "ʟɪꜱᴛ ᴀʟʟ ɢʀᴏᴜᴘꜱ"),
        ("/leave <chat_id>", "ʟᴇᴀᴠᴇ ᴀ ɢʀᴏᴜᴘ"),
        ("/disable <chat_id> [reason]", "ᴅɪꜱᴀʙʟᴇ ᴀ ɢʀᴏᴜᴘ"),
        ("/enable <chat_id>", "ʀᴇ-ᴇɴᴀʙʟᴇ ᴀ ɢʀᴏᴜᴘ"),
        ("/invite <chat_id>", "ɢᴇᴛ ɪɴᴠɪᴛᴇ ʟɪɴᴋ"),
        ("/verify", "ᴠᴇʀɪꜰʏ ᴏɴ/ᴏꜰꜰ (ɪɴ ɢʀᴏᴜᴘ)"),
        ("/resetallgroup", "ʀᴇꜱᴇᴛ ᴀʟʟ ɢʀᴏᴜᴘ ꜱᴇᴛᴛɪɴɢꜱ"),
        ("/settings · /details", "ɢʀᴏᴜᴘ ꜱᴇᴛᴛɪɴɢꜱ (ɢʀᴏᴜᴘ ᴀᴅᴍɪɴ)"),
    ]),
    "ctl": ("🤖 ʙᴏᴛ ᴄᴏɴᴛʀᴏʟ", [
        ("/panel", "ᴏᴘᴇɴ ᴛʜɪꜱ ᴘᴀɴᴇʟ"),
        ("/stats", "ʙᴏᴛ + ᴅʙ ꜱᴛᴀᴛꜱ"),
        ("/logs", "ɢᴇᴛ ʟᴏɢ ꜰɪʟᴇ"),
        ("/restart", "ʀᴇꜱᴛᴀʀᴛ ʙᴏᴛ"),
        ("/maintenance on|off", "ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ ᴍᴏᴅᴇ"),
        ("/tickets", "ꜱᴜᴘᴘᴏʀᴛ ɪɴʙᴏx"),
        ("/cancel", "ᴄᴀɴᴄᴇʟ ᴘᴇɴᴅɪɴɢ ʀᴇᴘʟʏ / ʙʀᴏᴀᴅᴄᴀꜱᴛ"),
        ("/contact", "(ᴜꜱᴇʀꜱ) ᴛᴀʟᴋ ᴛᴏ ᴀᴅᴍɪɴ"),
    ]),
}

CAT_ACTIONS = {   # quick one-tap buttons shown under each command list
    "usr": [("📄 ᴜꜱᴇʀꜱ ꜰɪʟᴇ", "ap:exp"), ("⚡ ʟɪᴠᴇ ᴜꜱᴇʀꜱ", "ap:users"), ("🚫 ʙᴀɴꜱ", "ap:bans")],
    "prem": [("📄 ᴘʀᴇᴍɪᴜᴍ ꜰɪʟᴇ", "ap:expp"), ("💎 ᴘʀᴇᴍɪᴜᴍ ᴘᴀɢᴇ", "ap:prem")],
    "bc": [("✍️ ᴄᴏᴍᴘᴏꜱᴇ ʙʀᴏᴀᴅᴄᴀꜱᴛ", "ap:compose")],
    "files": [("📊 ꜰɪʟᴇꜱ / ᴅʙ ꜱᴛᴀᴛꜱ", "ap:dash"), ("⚙️ ꜱᴇᴛᴛɪɴɢꜱ", "ap:set")],
    "grp": [("📄 ɢʀᴏᴜᴘꜱ ꜰɪʟᴇ", "ap:expc")],
    "ctl": [("📊 ꜱᴛᴀᴛꜱ", "ap:dash"), ("📜 ʟᴏɢꜱ", "ap:logs"),
            ("♻️ ʀᴇꜱᴛᴀʀᴛ", "ap:restart"), ("🖥 ꜱʏꜱᴛᴇᴍ", "ap:sys")],
}


def cmds_home():
    text = ("<b>📜 ᴀʟʟ ᴄᴏᴍᴍᴀɴᴅꜱ</b>\n━━━━━━━━━━━━━━━━━━\n"
            "ᴄʜᴏᴏꜱᴇ ᴀ ᴄᴀᴛᴇɢᴏʀʏ 👇  ᴇᴀᴄʜ ᴘᴀɢᴇ ʜᴀꜱ ᴛʜᴇ ᴄᴏᴍᴍᴀɴᴅꜱ + ᴏɴᴇ-ᴛᴀᴘ ᴀᴄᴛɪᴏɴꜱ.")
    items = list(CMD_CATS.items())
    rows = [[B(items[i][1][0], callback_data=f"ap:cm:{items[i][0]}")] +
            ([B(items[i + 1][1][0], callback_data=f"ap:cm:{items[i + 1][0]}")] if i + 1 < len(items) else [])
            for i in range(0, len(items), 2)]
    rows.append(BACK)
    return text, KB(rows)


def cmds_cat(key):
    title, cmds = CMD_CATS[key]
    lines = "\n".join(f"• <code>{esc(c)}</code>\n   <i>{d}</i>" for c, d in cmds)
    rows = [[B(t, callback_data=cb)] for t, cb in CAT_ACTIONS.get(key, [])]
    rows.append([B("↩️ ᴄᴀᴛᴇɢᴏʀɪᴇꜱ", callback_data="ap:cmds"), B("🏠 ʜᴏᴍᴇ", callback_data="ap:home")])
    return f"<b>{title}</b>\n━━━━━━━━━━━━━━━━━━\n{lines}", KB(rows)


async def users_page():
    total = await safe_count(db.total_users_count())
    prem = await safe_count(db.all_premium_users())
    d1, d7 = await active_since(86400), await active_since(7 * 86400)
    now_n = online_now()
    text = (
        "<b>👥 ᴜꜱᴇʀꜱ</b>\n━━━━━━━━━━━━━━━━━━\n"
        f"👥 ᴛᴏᴛᴀʟ : <code>{total}</code>\n"
        f"⚡ ᴏɴʟɪɴᴇ ɴᴏᴡ : <code>{now_n}</code>  <i>(ʟᴀꜱᴛ 5 ᴍɪɴ)</i>\n"
        f"📅 ᴀᴄᴛɪᴠᴇ ᴛᴏᴅᴀʏ (24ʜ) : <code>{d1}</code>\n"
        f"🗓 ᴀᴄᴛɪᴠᴇ 7 ᴅᴀʏꜱ : <code>{d7}</code>\n"
        f"💎 ᴘʀᴇᴍɪᴜᴍ : <code>{prem}</code>\n"
        f"⛔ ʙᴀɴɴᴇᴅ : <code>{len(temp.BANNED_USERS)}</code>\n\n"
        "🔎 ꜱᴇᴀʀᴄʜ ᴀ ᴜꜱᴇʀ : <code>/userinfo 123456789</code>\n"
        "<i>(ᴏʀ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜꜱᴇʀ'ꜱ ᴍᴇꜱꜱᴀɢᴇ ᴡɪᴛʜ /userinfo)</i>"
    )
    kb = KB([[B("🔄 ʀᴇꜰʀᴇꜱʜ", callback_data="ap:users"),
              B("📃 ᴇxᴘᴏʀᴛ ᴜꜱᴇʀꜱ", callback_data="ap:exp")], BACK])
    return text, kb


async def prem_page():
    now = datetime.datetime.now()
    rows = []
    try:
        cur = db.users.find({"expiry_time": {"$gt": now}}).sort("expiry_time", 1).limit(10)
        async for u in cur:
            exp = u["expiry_time"]
            left = max(0, int((exp - now).total_seconds()))
            rows.append(f"💎 <code>{u['id']}</code> – {get_readable_time(left) or '0s'} ʟᴇꜰᴛ")
    except Exception:
        logger.exception("prem_page failed")
    total = await safe_count(db.all_premium_users())
    body = "\n".join(rows) if rows else "<i>ɴᴏ ᴀᴄᴛɪᴠᴇ ᴘʀᴇᴍɪᴜᴍ ᴜꜱᴇʀꜱ</i>"
    text = (
        f"<b>💎 ᴘʀᴇᴍɪᴜᴍ</b>  •  <code>{total}</code> ᴀᴄᴛɪᴠᴇ\n━━━━━━━━━━━━━━━━━━\n"
        f"<b>ꜱᴏᴏɴᴇꜱᴛ ᴇxᴘɪʀɪɴɢ :</b>\n{body}\n\n"
        "➕ <code>/add_premium id 1 month</code>\n"
        "➖ <code>/remove_premium id</code>\n"
        "ᴏʀ ᴜꜱᴇ <code>/userinfo id</code> ꜰᴏʀ ᴏɴᴇ-ᴛᴀᴘ ᴀᴄᴛɪᴏɴꜱ."
    )
    return text, KB([BACK])


async def bans_page():
    ids = list(temp.BANNED_USERS)[:10]
    lines, btns = [], []
    for uid in ids:
        doc = None
        try:
            doc = await db.col.find_one({"id": uid})
        except Exception:
            pass
        name = esc((doc or {}).get("name") or "User")
        lines.append(f"🚫 {name} – <code>{uid}</code>")
        btns.append(B(f"✅ ᴜɴʙᴀɴ {uid}", callback_data=f"ap:unban:{uid}"))
    rows = [btns[i:i + 2] for i in range(0, len(btns), 2)]
    rows.append(BACK)
    body = "\n".join(lines) if lines else "<i>ɴᴏ ʙᴀɴɴᴇᴅ ᴜꜱᴇʀꜱ 🎉</i>"
    more = f"\n\n<i>ꜱʜᴏᴡɪɴɢ 10 ᴏꜰ {len(temp.BANNED_USERS)}</i>" if len(temp.BANNED_USERS) > 10 else ""
    return f"<b>🚫 ʙᴀɴɴᴇᴅ ᴜꜱᴇʀꜱ</b>\n━━━━━━━━━━━━━━━━━━\n{body}{more}", KB(rows)


async def settings_page():
    pm = await db.pm_search_status(temp.ME)
    mv = await db.movie_update_status(temp.ME)
    mt = await get_flag("MAINTENANCE", False)
    sp = await get_flag("SUPPORT_INBOX", True)
    text = (
        "<b>⚙️ ꜱᴇᴛᴛɪɴɢꜱ</b>\n━━━━━━━━━━━━━━━━━━\n"
        f"🔍 ᴘᴍ ꜱᴇᴀʀᴄʜ : {on_off(pm)}\n"
        f"🎞 ᴍᴏᴠɪᴇ ᴜᴘᴅᴀᴛᴇ ɴᴏᴛɪꜰʏ : {on_off(mv)}\n"
        f"🛠 ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ ᴍᴏᴅᴇ : {on_off(mt)}\n"
        f"📨 ᴄᴏɴᴛᴀᴄᴛ-ᴀᴅᴍɪɴ ɪɴʙᴏx : {on_off(sp)}\n\n"
        "<i>ᴛᴀᴘ ᴀ ʙᴜᴛᴛᴏɴ ᴛᴏ ᴛᴏɢɢʟᴇ</i>"
    )
    kb = KB([
        [B(f"🔍 ᴘᴍ ꜱᴇᴀʀᴄʜ: {'ᴏɴ' if pm else 'ᴏꜰꜰ'}", callback_data="ap:tgl:pm")],
        [B(f"🎞 ᴍᴏᴠɪᴇ ᴜᴘᴅᴀᴛᴇ: {'ᴏɴ' if mv else 'ᴏꜰꜰ'}", callback_data="ap:tgl:mv")],
        [B(f"🛠 ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ: {'ᴏɴ' if mt else 'ᴏꜰꜰ'}", callback_data="ap:tgl:mt")],
        [B(f"📨 ɪɴʙᴏx: {'ᴏɴ' if sp else 'ᴏꜰꜰ'}", callback_data="ap:tgl:sp")],
        BACK,
    ])
    return text, kb


async def inbox_page():
    rows, btns = [], []
    try:
        cur = TICKETS.find({"status": "open"}).sort("updated", -1).limit(8)
        async for t in cur:
            label = f"#{t['_id']} • {t.get('name', 'User')[:16]} ({t.get('count', 0)})"
            btns.append([B(f"📨 {label}", callback_data=f"tk:view:{t['_id']}")])
    except Exception:
        logger.exception("inbox_page failed")
    total = await safe_count(TICKETS.count_documents({"status": "open"}))
    body = "ᴛᴀᴘ ᴀ ᴛɪᴄᴋᴇᴛ ᴛᴏ ᴏᴘᴇɴ ɪᴛ 👇" if btns else "<i>ɴᴏ ᴏᴘᴇɴ ᴛɪᴄᴋᴇᴛꜱ – ᴀʟʟ ᴄʟᴇᴀʀ ✨</i>"
    btns.append(BACK)
    return f"<b>📨 ꜱᴜᴘᴘᴏʀᴛ ɪɴʙᴏx</b>  •  <code>{total}</code> ᴏᴘᴇɴ\n━━━━━━━━━━━━━━━━━━\n{body}", KB(btns)


async def broadcast_page():
    users = await safe_count(db.total_users_count())
    text = (
        "<b>📢 ʙʀᴏᴀᴅᴄᴀꜱᴛ</b>\n━━━━━━━━━━━━━━━━━━\n"
        f"👥 ʀᴇᴄɪᴘɪᴇɴᴛꜱ : <code>{users}</code>\n\n"
        "1️⃣ ᴛᴀᴘ <b>✍️ ᴄᴏᴍᴘᴏꜱᴇ</b>\n"
        "2️⃣ ꜱᴇɴᴅ ᴛʜᴇ ᴍᴇꜱꜱᴀɢᴇ (ᴛᴇxᴛ / ᴘʜᴏᴛᴏ / ᴠɪᴅᴇᴏ / ꜰɪʟᴇ)\n"
        "3️⃣ ᴄᴏɴꜰɪʀᴍ – ᴅᴏɴᴇ ✅\n\n"
        "<i>ʟɪᴠᴇ ᴘʀᴏɢʀᴇꜱꜱ ɪꜱ ꜱʜᴏᴡɴ ᴀɴᴅ ʏᴏᴜ ᴄᴀɴ ᴄᴀɴᴄᴇʟ ᴀɴʏᴛɪᴍᴇ.</i>"
    )
    return text, KB([[B("✍️ ᴄᴏᴍᴘᴏꜱᴇ", callback_data="ap:compose")], BACK])


async def user_card(bot, uid):
    """Build the /userinfo card (text, keyboard)."""
    doc = await db.col.find_one({"id": uid})
    if not doc:
        return None, None
    try:
        u = await bot.get_users(uid)
        name = esc(u.first_name)
        uname = f"@{u.username}" if u.username else "—"
    except Exception:
        name, uname = esc(doc.get("name")), "—"
    ban = await db.get_ban_status(uid)
    banned = bool(ban.get("is_banned"))
    premium = await db.has_premium_access(uid)
    pdoc = await db.get_user(uid) or {}
    exp = pdoc.get("expiry_time")
    exp_s = exp.strftime("%d %b %Y") if premium and isinstance(exp, datetime.datetime) else "—"
    daily = await db.daily.find_one({"_id": uid}) or {}
    tix = await safe_count(TICKETS.count_documents({"uid": uid}))
    text = (
        "<b>👤 ᴜꜱᴇʀ ᴄᴀʀᴅ</b>\n━━━━━━━━━━━━━━━━━━\n"
        f"🏷 ɴᴀᴍᴇ : <a href='tg://user?id={uid}'>{name}</a>\n"
        f"🔗 ᴜꜱᴇʀɴᴀᴍᴇ : {esc(uname)}\n"
        f"🆔 ɪᴅ : <code>{uid}</code>\n"
        f"💎 ᴘʀᴇᴍɪᴜᴍ : {'💎 ʏᴇꜱ (till ' + exp_s + ')' if premium else '➖ ɴᴏ'}\n"
        f"⛔ ʙᴀɴɴᴇᴅ : {'🚫 ʏᴇꜱ – ' + esc(ban.get('ban_reason')) if banned else '✅ ɴᴏ'}\n"
        f"🎬 ꜰɪʟᴇꜱ ᴛᴏᴅᴀʏ : <code>{daily.get('sent', 0)}</code>\n"
        f"📨 ᴛɪᴄᴋᴇᴛꜱ : <code>{tix}</code>"
    )
    rows = [
        [B("✍️ ᴍᴇꜱꜱᴀɢᴇ", callback_data=f"ap:msg:{uid}"),
         B("✅ ᴜɴʙᴀɴ" if banned else "🚫 ʙᴀɴ",
           callback_data=f"ap:{'unban' if banned else 'ban'}:{uid}:card")],
        [B("💎 +7ᴅ", callback_data=f"ap:gp:{uid}:7"), B("💎 +30ᴅ", callback_data=f"ap:gp:{uid}:30"),
         B("💎 +1ʏ", callback_data=f"ap:gp:{uid}:365")],
    ]
    if premium:
        rows.append([B("➖ ʀᴇᴍᴏᴠᴇ ᴘʀᴇᴍɪᴜᴍ", callback_data=f"ap:rp:{uid}")])
    return text, KB(rows)


# ----------------------------------------------------- admin commands ------
@Client.on_message(filters.private & filters.command(["panel", "admin"]) & filters.user(ADMINS))
async def panel_cmd(bot, message):
    await ensure_indexes()
    await message.reply_text(await home_text(), reply_markup=await home_kb(), parse_mode=HTML)


@Client.on_message(filters.private & filters.command("tickets") & filters.user(ADMINS))
async def tickets_cmd(bot, message):
    text, kb = await inbox_page()
    await message.reply_text(text, reply_markup=kb, parse_mode=HTML)


@Client.on_message(filters.private & filters.command("userinfo") & filters.user(ADMINS))
async def userinfo_cmd(bot, message):
    uid = None
    if len(message.command) > 1 and message.command[1].lstrip("-").isdigit():
        uid = int(message.command[1])
    elif message.reply_to_message:
        # swipe-replied ticket message -> its user, otherwise the sender of that message
        m = await TMAP.find_one({"admin": message.from_user.id, "mid": message.reply_to_message.id})
        if m:
            uid = m["uid"]
        elif message.reply_to_message.from_user:
            uid = message.reply_to_message.from_user.id
    if uid is None:
        return await message.reply_text("<b>Usage:</b> <code>/userinfo user_id</code> (or reply to a user's message)",
                                        parse_mode=HTML)
    text, kb = await user_card(bot, uid)
    if not text:
        return await message.reply_text("<b>⚠️ ᴜꜱᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ ɪɴ ᴅᴀᴛᴀʙᴀꜱᴇ.</b>", parse_mode=HTML)
    await message.reply_text(text, reply_markup=kb, parse_mode=HTML)


@Client.on_message(filters.private & filters.command("maintenance") & filters.user(ADMINS))
async def maintenance_cmd(bot, message):
    if len(message.command) < 2 or message.command[1].lower() not in ("on", "off"):
        cur = await get_flag("MAINTENANCE", False)
        return await message.reply_text(
            f"<b>🛠 ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ :</b> {on_off(cur)}\n<code>/maintenance on</code> | <code>/maintenance off</code>",
            parse_mode=HTML)
    val = message.command[1].lower() == "on"
    await set_flag("MAINTENANCE", val)
    await message.reply_text(f"<b>🛠 ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ ɴᴏᴡ {on_off(val)}</b>", parse_mode=HTML)


@Client.on_message(filters.private & filters.command("cancel") & filters.user(ADMINS))
async def cancel_cmd(bot, message):
    aid = message.from_user.id
    had = any([REPLYING.pop(aid, None), COMPOSE.pop(aid, None), PENDING_BC.pop(aid, None)])
    await message.reply_text("<b>✅ ᴄᴀɴᴄᴇʟʟᴇᴅ.</b>" if had else "<b>ɴᴏᴛʜɪɴɢ ᴛᴏ ᴄᴀɴᴄᴇʟ.</b>", parse_mode=HTML)


# --------------------------------------------------- panel callbacks -------
async def _toggle(key):
    if key == "pm":
        await db.update_pm_search_status(temp.ME, not await db.pm_search_status(temp.ME))
    elif key == "mv":
        await db.update_movie_update_status(temp.ME, not await db.movie_update_status(temp.ME))
    elif key == "mt":
        await set_flag("MAINTENANCE", not await get_flag("MAINTENANCE", False))
    elif key == "sp":
        await set_flag("SUPPORT_INBOX", not await get_flag("SUPPORT_INBOX", True))


async def _ban(bot, uid, by):
    if uid in ADMINS:
        return False
    await db.ban_user(uid, f"Banned by admin {by}")
    if uid not in temp.BANNED_USERS:
        temp.BANNED_USERS.append(uid)
    CONTACT.pop(uid, None)
    return True


async def _unban(uid):
    await db.remove_ban(uid)
    if uid in temp.BANNED_USERS:
        temp.BANNED_USERS.remove(uid)


@Client.on_callback_query(filters.regex(r"^(ap|tk):") & filters.user(ADMINS), group=-3)
async def admin_callbacks(bot, query):
    await ensure_indexes()
    parts = query.data.split(":")
    scope, action = parts[0], parts[1]
    arg = parts[2] if len(parts) > 2 else None
    aid = query.from_user.id
    try:
        if scope == "ap":
            if action == "home":
                await show(query, await home_text(), await home_kb())
            elif action == "dash":
                kb = KB([[B("🔄 ʀᴇꜰʀᴇꜱʜ", callback_data="ap:dash")], BACK])
                await show(query, await dash_text(), kb)
            elif action == "sys":
                kb = KB([[B("🔄 ʀᴇꜰʀᴇꜱʜ", callback_data="ap:sys")], BACK])
                await show(query, sys_text(), kb)
            elif action == "cmds":
                await show(query, *cmds_home())
            elif action == "cm":
                if arg in CMD_CATS:
                    await show(query, *cmds_cat(arg))
            elif action == "expc":
                await query.answer("📃 ᴘʀᴇᴘᴀʀɪɴɢ ꜰɪʟᴇ…")
                lines = ["id,title,disabled"]
                async for c in await db.get_all_chats():
                    t = str(c.get("title", "")).replace(",", " ").replace("\n", " ")
                    lines.append(f"{c['id']},{t},{c.get('chat_status', {}).get('is_disabled', False)}")
                bio = io.BytesIO("\n".join(lines).encode("utf-8"))
                bio.name = "groups_export.csv"
                await query.message.reply_document(bio, caption=f"💬 <b>{len(lines) - 1}</b> ɢʀᴏᴜᴘꜱ", parse_mode=HTML)
            elif action == "expp":
                await query.answer("📃 ᴘʀᴇᴘᴀʀɪɴɢ ꜰɪʟᴇ…")
                lines = ["id,expires"]
                async for u in db.users.find({"expiry_time": {"$gt": datetime.datetime.now()}}):
                    lines.append(f"{u['id']},{u['expiry_time']:%Y-%m-%d %H:%M}")
                bio = io.BytesIO("\n".join(lines).encode("utf-8"))
                bio.name = "premium_export.csv"
                await query.message.reply_document(bio, caption=f"💎 <b>{len(lines) - 1}</b> ᴘʀᴇᴍɪᴜᴍ ᴜꜱᴇʀꜱ", parse_mode=HTML)
            elif action == "logs":
                try:
                    await query.message.reply_document("DreamXlogs.txt", caption="📑 <b>ʟᴏɢꜱ</b>", parse_mode=HTML)
                    await query.answer()
                except Exception:
                    await query.answer("⚠️ ʟᴏɢ ꜰɪʟᴇ ɴᴏᴛ ꜰᴏᴜɴᴅ", show_alert=True)
            elif action == "restart":
                await show(query, "<b>♻️ ʀᴇꜱᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ?</b>\n<i>ɪᴛ ʙᴇᴄᴏᴍᴇꜱ ᴏꜰꜰʟɪɴᴇ ꜰᴏʀ ᴀ ꜰᴇᴡ ꜱᴇᴄᴏɴᴅꜱ.</i>",
                           KB([[B("✅ ʏᴇꜱ, ʀᴇꜱᴛᴀʀᴛ", callback_data="ap:restartyes"),
                                B("✖️ ɴᴏ", callback_data="ap:cm:ctl")]]))
            elif action == "restartyes":
                await query.answer("♻️ Restarting…")
                await query.message.edit_text("<b><i>ʙᴏᴛ ɪꜱ ʀᴇꜱᴛᴀʀᴛɪɴɢ…</i></b>", parse_mode=HTML)
                await asyncio.sleep(2)
                os.execl(sys.executable, sys.executable, *sys.argv)
            elif action == "users":
                await show(query, *await users_page())
            elif action == "prem":
                await show(query, *await prem_page())
            elif action == "bans":
                await show(query, *await bans_page())
            elif action == "set":
                await show(query, *await settings_page())
            elif action == "inbox":
                await show(query, *await inbox_page())
            elif action == "bc":
                await show(query, *await broadcast_page())
            elif action == "close":
                await query.message.delete()
            elif action == "tgl":
                await _toggle(arg)
                await query.answer("✅ ᴜᴘᴅᴀᴛᴇᴅ")
                await show(query, *await settings_page())
            elif action == "exp":
                await query.answer("📃 ᴘʀᴇᴘᴀʀɪɴɢ ꜰɪʟᴇ…")
                lines = ["id,name,banned"]
                async for u in await db.get_all_users():
                    nm = str(u.get("name", "")).replace(",", " ").replace("\n", " ")
                    lines.append(f"{u['id']},{nm},{u.get('ban_status', {}).get('is_banned', False)}")
                bio = io.BytesIO("\n".join(lines).encode("utf-8"))
                bio.name = "users_export.csv"
                await query.message.reply_document(bio, caption=f"📃 <b>{len(lines) - 1}</b> ᴜꜱᴇʀꜱ", parse_mode=HTML)
            elif action == "ui":
                text, kb = await user_card(bot, int(arg))
                if not text:
                    await query.answer("User not found", show_alert=True)
                else:
                    await query.message.reply_text(text, reply_markup=kb, parse_mode=HTML)
                    await query.answer()
            elif action == "ban":
                uid = int(arg)
                ok = await _ban(bot, uid, aid)
                await query.answer("🚫 ᴜꜱᴇʀ ʙᴀɴɴᴇᴅ" if ok else "⚠️ ᴄᴀɴ'ᴛ ʙᴀɴ ᴀɴ ᴀᴅᴍɪɴ", show_alert=not ok)
                if ok and len(parts) > 3:
                    text, kb = await user_card(bot, uid)
                    await show(query, text, kb)
            elif action == "unban":
                uid = int(arg)
                await _unban(uid)
                await query.answer("✅ ᴜɴʙᴀɴɴᴇᴅ")
                if len(parts) > 3:
                    text, kb = await user_card(bot, uid)
                    await show(query, text, kb)
                else:
                    await show(query, *await bans_page())
            elif action == "gp":
                uid, days = int(arg), int(parts[3])
                exp = datetime.datetime.now() + datetime.timedelta(days=days)
                await db.update_user({"id": uid, "expiry_time": exp})
                try:
                    await bot.send_message(
                        uid, f"<b>🎉 ʏᴏᴜ ᴡᴇʀᴇ ɢɪᴠᴇɴ 💎 ᴘʀᴇᴍɪᴜᴍ ꜰᴏʀ {days} ᴅᴀʏꜱ!\n"
                             f"⌛ ᴇxᴘɪʀʏ : {exp.strftime('%d %b %Y')}</b>", parse_mode=HTML)
                except Exception:
                    pass
                await query.answer(f"💎 +{days}d granted")
                text, kb = await user_card(bot, uid)
                await show(query, text, kb)
            elif action == "rp":
                uid = int(arg)
                await db.remove_premium_access(uid)
                await query.answer("➖ ᴘʀᴇᴍɪᴜᴍ ʀᴇᴍᴏᴠᴇᴅ")
                text, kb = await user_card(bot, uid)
                await show(query, text, kb)
            elif action == "msg":
                REPLYING[aid] = (int(arg), 0, time.time())
                await query.answer()
                await query.message.reply_text(
                    f"<b>✍️ ꜱᴇɴᴅ ʏᴏᴜʀ ᴍᴇꜱꜱᴀɢᴇ ɴᴏᴡ ꜰᴏʀ</b> <code>{arg}</code>\n<i>/cancel ᴛᴏ ꜱᴛᴏᴘ</i>", parse_mode=HTML)
            elif action == "compose":
                COMPOSE[aid] = time.time()
                await query.answer()
                await query.message.reply_text(
                    "<b>✍️ ꜱᴇɴᴅ ᴛʜᴇ ᴍᴇꜱꜱᴀɢᴇ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ʙʀᴏᴀᴅᴄᴀꜱᴛ.</b>\n<i>/cancel ᴛᴏ ꜱᴛᴏᴘ</i>", parse_mode=HTML)
            elif action == "bcgo":
                await query.answer("📤 ꜱᴛᴀʀᴛɪɴɢ…")
                msg = PENDING_BC.pop(aid, None)
                if msg is None:
                    await query.message.edit_text("<b>⚠️ ɴᴏᴛʜɪɴɢ ᴘᴇɴᴅɪɴɢ.</b>", parse_mode=HTML)
                else:
                    await run_broadcast(bot, query.message, msg)
            elif action == "bcno":
                PENDING_BC.pop(aid, None)
                await query.message.edit_text("<b>❌ ʙʀᴏᴀᴅᴄᴀꜱᴛ ᴄᴀɴᴄᴇʟʟᴇᴅ.</b>", parse_mode=HTML)
            elif action == "bcstop":
                BC["cancel"] = True
                await query.answer("⏹ ꜱᴛᴏᴘᴘɪɴɢ…")
        else:  # tk
            tid = int(arg)
            t = await TICKETS.find_one({"_id": tid})
            if not t:
                await query.answer("Ticket not found", show_alert=True)
            elif action == "view":
                text = (f"<b>📨 ᴛɪᴄᴋᴇᴛ #{tid}</b>\n━━━━━━━━━━━━━━━━━━\n"
                        f"👤 <a href='tg://user?id={t['uid']}'>{esc(t.get('name'))}</a> "
                        f"{('@' + esc(t['uname'])) if t.get('uname') else ''}\n"
                        f"🆔 <code>{t['uid']}</code>\n"
                        f"💬 ᴍᴇꜱꜱᴀɢᴇꜱ : <code>{t.get('count', 0)}</code>\n"
                        f"📌 ꜱᴛᴀᴛᴜꜱ : {'📬 ᴏᴘᴇɴ' if t['status'] == 'open' else '📪 ᴄʟᴏꜱᴇᴅ'}")
                kb = ticket_kb(tid, t["uid"], t["status"] != "open")
                kb.inline_keyboard.append([B("⬅️ ɪɴʙᴏx", callback_data="ap:inbox")])
                await show(query, text, kb)
            elif action == "reply":
                REPLYING[aid] = (t["uid"], tid, time.time())
                await query.answer("✍️ Send your reply now")
                await query.message.reply_text(
                    f"<b>✍️ ꜱᴇɴᴅ ʏᴏᴜʀ ʀᴇᴘʟʏ ꜰᴏʀ ᴛɪᴄᴋᴇᴛ #{tid} ɴᴏᴡ.</b>\n<i>/cancel ᴛᴏ ꜱᴛᴏᴘ</i>", parse_mode=HTML)
            elif action == "close":
                await TICKETS.update_one({"_id": tid}, {"$set": {"status": "closed"}})
                CONTACT.pop(t["uid"], None)
                try:
                    await bot.send_message(
                        t["uid"], f"<b>✅ ʏᴏᴜʀ ᴛɪᴄᴋᴇᴛ #{tid} ʜᴀꜱ ʙᴇᴇɴ ᴄʟᴏꜱᴇᴅ.</b>\n"
                                  "ɴᴇᴇᴅ ᴍᴏʀᴇ ʜᴇʟᴘ? ꜱᴇɴᴅ /contact ᴀɢᴀɪɴ.", parse_mode=HTML)
                except Exception:
                    pass
                await query.answer("✅ Ticket closed")
                try:
                    await query.message.edit_reply_markup(ticket_kb(tid, t["uid"], True))
                except Exception:
                    pass
            elif action == "open":
                await TICKETS.update_one({"_id": tid}, {"$set": {"status": "open"}})
                await query.answer("🔓 Reopened")
                try:
                    await query.message.edit_reply_markup(ticket_kb(tid, t["uid"], False))
                except Exception:
                    pass
    except Exception:
        logger.exception("admin_callbacks failed for %s", query.data)
        try:
            await query.answer("⚠️ Something went wrong – check logs", show_alert=True)
        except Exception:
            pass
    query.stop_propagation()


# ---------------------------------------------------------- broadcast ------
async def run_broadcast(bot, status_msg, src):
    if _bc_lock.locked():
        return await status_msg.edit_text("<b>⚠️ ᴀɴᴏᴛʜᴇʀ ʙʀᴏᴀᴅᴄᴀꜱᴛ ɪꜱ ʀᴜɴɴɪɴɢ.</b>", parse_mode=HTML)
    async with _bc_lock:
        BC["cancel"] = False
        total = await safe_count(db.total_users_count())
        done = ok = blocked = failed = 0
        stop_kb = KB([[B("⏹ ꜱᴛᴏᴘ", callback_data="ap:bcstop")]])
        last_edit = 0.0
        async for user in await db.get_all_users():
            if BC["cancel"]:
                break
            uid = int(user["id"])
            if uid in temp.BANNED_USERS:
                continue
            try:
                try:
                    await src.copy(uid)
                except FloodWait as e:
                    await asyncio.sleep(e.value + 1)
                    await src.copy(uid)
                ok += 1
            except SEND_ERRORS:
                blocked += 1
            except Exception:
                failed += 1
            done += 1
            if done % 25 == 0:
                await asyncio.sleep(1)
            if time.time() - last_edit > 4:
                last_edit = time.time()
                pct = done / total * 100 if total else 100
                try:
                    await status_msg.edit_text(
                        f"<b>📤 ʙʀᴏᴀᴅᴄᴀꜱᴛɪɴɢ…</b>\n{bar(pct)} <code>{pct:.0f}%</code>\n"
                        f"✅ <code>{ok}</code>  🚫 <code>{blocked}</code>  ❌ <code>{failed}</code>",
                        reply_markup=stop_kb, parse_mode=HTML)
                except Exception:
                    pass
        await status_msg.edit_text(
            f"<b>{'⏹ ʙʀᴏᴀᴅᴄᴀꜱᴛ ꜱᴛᴏᴘᴘᴇᴅ' if BC['cancel'] else '✅ ʙʀᴏᴀᴅᴄᴀꜱᴛ ꜰɪɴɪꜱʜᴇᴅ'}</b>\n\n"
            f"✅ ᴅᴇʟɪᴠᴇʀᴇᴅ : <code>{ok}</code>\n🚫 ʙʟᴏᴄᴋᴇᴅ/ᴅᴇʟᴇᴛᴇᴅ : <code>{blocked}</code>\n"
            f"❌ ꜰᴀɪʟᴇᴅ : <code>{failed}</code>", parse_mode=HTML)


# ------------------------------------------------ admin message routing ----
@Client.on_message(filters.private & filters.incoming & filters.user(ADMINS)
                   & ~filters.regex(r"^/") & ~filters.service, group=-2)
async def admin_router(bot, message):
    """Routes an admin's message to: broadcast composer, armed [Reply] target,
    or the user whose ticket message was swipe-replied."""
    aid = message.from_user.id

    # 1) broadcast composer
    ts = COMPOSE.get(aid)
    if ts and time.time() - ts < REPLY_TTL:
        COMPOSE.pop(aid, None)
        PENDING_BC[aid] = message
        total = await safe_count(db.total_users_count())
        await message.reply_text(
            f"<b>📢 ꜱᴇɴᴅ ᴛʜɪꜱ ᴍᴇꜱꜱᴀɢᴇ ᴛᴏ <code>{total}</code> ᴜꜱᴇʀꜱ?</b>",
            reply_to_message_id=message.id, parse_mode=HTML,
            reply_markup=KB([[B("✅ ꜱᴇɴᴅ", callback_data="ap:bcgo"), B("❌ ᴄᴀɴᴄᴇʟ", callback_data="ap:bcno")]]))
        return message.stop_propagation()

    # 2) swipe-reply on a ticket message / 3) armed [Reply] button
    target = None
    if message.reply_to_message:
        m = await TMAP.find_one({"admin": aid, "mid": message.reply_to_message.id})
        if m:
            target = (m["uid"], m["tid"])
    if target is None:
        armed = REPLYING.get(aid)
        if armed and time.time() - armed[2] < REPLY_TTL:
            target = (armed[0], armed[1])
            REPLYING.pop(aid, None)
    if target is None:
        return  # normal admin message – let other handlers deal with it

    uid, tid = target
    if await deliver_to_user(bot, message, uid, tid):
        try:
            await message.react("👍")
        except Exception:
            _auto_delete(await message.reply_text("<b>✅ ᴅᴇʟɪᴠᴇʀᴇᴅ</b>", parse_mode=HTML), 4)
    else:
        await message.reply_text("<b>❌ ᴄᴏᴜʟᴅ ɴᴏᴛ ᴅᴇʟɪᴠᴇʀ – ᴜꜱᴇʀ ᴍᴀʏ ʜᴀᴠᴇ ʙʟᴏᴄᴋᴇᴅ ᴛʜᴇ ʙᴏᴛ.</b>", parse_mode=HTML)
    message.stop_propagation()


# ----------------------------------------------------------- user side -----
def _contact_active(uid) -> bool:
    ts = CONTACT.get(uid)
    if ts and time.time() - ts < CONTACT_TTL:
        return True
    CONTACT.pop(uid, None)
    return False


def _flooding(uid) -> bool:
    now = time.time()
    hits = [t for t in FLOOD.get(uid, []) if now - t < FLOOD_WINDOW]
    hits.append(now)
    FLOOD[uid] = hits
    return len(hits) > FLOOD_MAX


CONTACT_PROMPT = (
    "<b>📨 ᴄᴏɴᴛᴀᴄᴛ ᴀᴅᴍɪɴ</b>\n━━━━━━━━━━━━━━━━━━\n"
    "✍️ ᴡʀɪᴛᴇ ʏᴏᴜʀ ᴍᴇꜱꜱᴀɢᴇ ɴᴏᴡ – ᴛᴇxᴛ, ᴘʜᴏᴛᴏ, ᴠɪᴅᴇᴏ, ꜰɪʟᴇ ᴏʀ ᴠᴏɪᴄᴇ ᴀʀᴇ ᴀʟʟ ꜰɪɴᴇ.\n"
    "ᴀɴ ᴀᴅᴍɪɴ ᴡɪʟʟ ʀᴇᴘʟʏ ʜᴇʀᴇ ɪɴ ᴛʜɪꜱ ᴄʜᴀᴛ 💬\n\n"
    "<i>⏳ ꜱᴇꜱꜱɪᴏɴ ᴇɴᴅꜱ ᴀꜰᴛᴇʀ 10 ᴍɪɴ ᴏꜰ ɪɴᴀᴄᴛɪᴠɪᴛʏ.</i>"
)
CANCEL_KB = KB([[B("❌ ᴄᴀɴᴄᴇʟ", callback_data="ct:cancel")]])


async def start_contact(bot, user, reply):
    if user.id in temp.BANNED_USERS:
        return
    if not await get_flag("SUPPORT_INBOX", True):
        return await reply("<b>📪 ꜱᴜᴘᴘᴏʀᴛ ɪɴʙᴏx ɪꜱ ᴄʟᴏꜱᴇᴅ ʀɪɢʜᴛ ɴᴏᴡ. ᴘʟᴇᴀꜱᴇ ᴛʀʏ ʟᴀᴛᴇʀ.</b>")
    if not ADMIN_IDS:
        return await reply("<b>⚠️ ɴᴏ ᴀᴅᴍɪɴ ɪꜱ ᴄᴏɴꜰɪɢᴜʀᴇᴅ.</b>")
    CONTACT[user.id] = time.time()
    open_t = await TICKETS.find_one({"uid": user.id, "status": "open"})
    extra = f"\n\n🎫 ᴄᴏɴᴛɪɴᴜɪɴɢ ᴛɪᴄᴋᴇᴛ <code>#{open_t['_id']}</code>" if open_t else ""
    await reply(CONTACT_PROMPT + extra)


@Client.on_message(filters.private & filters.command(["contact", "support"]) & filters.incoming, group=-4)
async def contact_cmd(bot, message):
    if not message.from_user:
        return
    await start_contact(bot, message.from_user,
                        lambda t: message.reply_text(t, reply_markup=CANCEL_KB, parse_mode=HTML))
    message.stop_propagation()


@Client.on_callback_query(filters.regex(r"^ct:"), group=-3)
async def contact_callbacks(bot, query):
    action = query.data.split(":")[1]
    try:
        if action == "start":
            await query.answer()
            await start_contact(bot, query.from_user,
                                lambda t: query.message.reply_text(t, reply_markup=CANCEL_KB, parse_mode=HTML))
        elif action == "cancel":
            CONTACT.pop(query.from_user.id, None)
            await query.answer("Cancelled")
            try:
                await query.message.edit_text("<b>❌ ᴄᴏɴᴛᴀᴄᴛ ᴍᴏᴅᴇ ᴄʟᴏꜱᴇᴅ.</b>", parse_mode=HTML)
            except Exception:
                pass
    except Exception:
        logger.exception("contact_callbacks failed")
    query.stop_propagation()


@Client.on_message(filters.private & filters.incoming & ~filters.user(ADMINS) & ~filters.service, group=-5)
async def maintenance_gate(bot, message):
    if not message.from_user or message.from_user.id in temp.BANNED_USERS:
        return
    if not await get_flag("MAINTENANCE", False):
        return
    cmd = (message.text or "").split()[:1]
    if cmd and cmd[0].lstrip("/").split("@")[0].lower() in ("contact", "support"):
        return
    if _contact_active(message.from_user.id) and not (message.text or "").startswith("/"):
        return
    await message.reply_text(
        "<b>🛠 ʙᴏᴛ ɪꜱ ᴜɴᴅᴇʀ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ</b>\n\n"
        "ᴡᴇ'ʟʟ ʙᴇ ʙᴀᴄᴋ ꜱʜᴏʀᴛʟʏ ⏳\nɪꜰ ɪᴛ'ꜱ ᴜʀɢᴇɴᴛ, ʏᴏᴜ ᴄᴀɴ ᴍᴇꜱꜱᴀɢᴇ ᴛʜᴇ ᴀᴅᴍɪɴ 👇",
        reply_markup=KB([[B("📨 ᴄᴏɴᴛᴀᴄᴛ ᴀᴅᴍɪɴ", callback_data="ct:start")]]), parse_mode=HTML)
    message.stop_propagation()


@Client.on_message(filters.private & filters.incoming & filters.regex(r"^/") & ~filters.user(ADMINS), group=-4)
async def leave_contact_on_command(bot, message):
    """Any other command (/start, /plan ...) ends contact mode, no propagation stop."""
    if not message.from_user:
        return
    word = (message.text or "").split()[0].lstrip("/").split("@")[0].lower()
    if word not in ("contact", "support"):
        CONTACT.pop(message.from_user.id, None)


@Client.on_message(filters.private & filters.incoming & ~filters.user(ADMINS)
                   & ~filters.regex(r"^/") & ~filters.service, group=-2)
async def user_to_admin_inbox(bot, message):
    user = message.from_user
    if not user or not _contact_active(user.id) or user.id in temp.BANNED_USERS:
        return
    if not await get_flag("SUPPORT_INBOX", True):
        CONTACT.pop(user.id, None)
        return
    if _flooding(user.id):
        _auto_delete(await message.reply_text("<b>⏳ ꜱʟᴏᴡ ᴅᴏᴡɴ ᴀ ʙɪᴛ – ᴛᴏᴏ ᴍᴀɴʏ ᴍᴇꜱꜱᴀɢᴇꜱ.</b>", parse_mode=HTML), 5)
        return message.stop_propagation()
    await ensure_indexes()
    try:
        ticket, is_new = await get_or_create_ticket(user)
    except Exception:
        logger.exception("ticket create failed")
        await message.reply_text("<b>⚠️ ꜱᴏᴍᴇᴛʜɪɴɢ ᴡᴇɴᴛ ᴡʀᴏɴɢ. ᴘʟᴇᴀꜱᴇ ᴛʀʏ ᴀɢᴀɪɴ.</b>", parse_mode=HTML)
        return message.stop_propagation()
    tid = ticket["_id"]
    premium = await db.has_premium_access(user.id)
    uname = f" (@{esc(user.username)})" if user.username else ""
    header = (
        f"📨 <b>{'ɴᴇᴡ ᴛɪᴄᴋᴇᴛ' if is_new else 'ɴᴇᴡ ᴍᴇꜱꜱᴀɢᴇ'}</b>  •  <code>#{tid}</code>\n"
        f"👤 <a href='tg://user?id={user.id}'>{esc(user.first_name)}</a>{uname}\n"
        f"🆔 <code>{user.id}</code>  •  {'💎 ᴘʀᴇᴍɪᴜᴍ' if premium else '🆓 ꜰʀᴇᴇ'}\n"
        f"🕒 {now_ist()}"
    )
    delivered = 0
    for aid in ADMIN_IDS:
        try:
            h = await bot.send_message(aid, header, reply_markup=ticket_kb(tid, user.id), parse_mode=HTML)
            await remember(aid, h.id, user.id, tid)
            c = await message.copy(aid, reply_to_message_id=h.id)
            await remember(aid, c.id, user.id, tid)
            delivered += 1
        except FloodWait as e:
            await asyncio.sleep(min(e.value, 5))
        except Exception:
            logger.warning("could not deliver ticket to admin %s", aid, exc_info=True)
    if delivered:
        CONTACT[user.id] = time.time()
        await TICKETS.update_one({"_id": tid}, {"$inc": {"count": 1},
                                                "$set": {"updated": datetime.datetime.utcnow()}})
        if is_new:
            await message.reply_text(
                f"<b>✅ ꜱᴇɴᴛ ᴛᴏ ᴀᴅᴍɪɴ!</b>  🎫 <code>#{tid}</code>\n"
                "ʏᴏᴜ'ʟʟ ɢᴇᴛ ᴀ ʀᴇᴘʟʏ ʜᴇʀᴇ. ʏᴏᴜ ᴄᴀɴ ᴋᴇᴇᴘ ꜱᴇɴᴅɪɴɢ ᴍᴏʀᴇ ᴍᴇꜱꜱᴀɢᴇꜱ.",
                reply_markup=CANCEL_KB, parse_mode=HTML)
        else:
            try:
                await message.react("👍")
            except Exception:
                _auto_delete(await message.reply_text("<b>✅ ꜱᴇɴᴛ</b>", parse_mode=HTML), 3)
    else:
        await message.reply_text("<b>❌ ᴀᴅᴍɪɴ ɪꜱ ᴜɴʀᴇᴀᴄʜᴀʙʟᴇ ʀɪɢʜᴛ ɴᴏᴡ. ᴛʀʏ ʟᴀᴛᴇʀ.</b>", parse_mode=HTML)
    message.stop_propagation()


# ------------------------------------------------- admin-only guard -------
@Client.on_callback_query(filters.regex(r"^(ap|tk):") & ~filters.user(ADMINS), group=-3)
async def not_admin_callback(bot, query):
    await query.answer()   # silent: the panel stays invisible to non-admins
    query.stop_propagation()


@Client.on_message(filters.private & filters.command(["panel", "admin", "tickets", "userinfo", "maintenance"])
                   & ~filters.user(ADMINS), group=-4)
async def not_admin_command(bot, message):
    message.stop_propagation()   # silent: no reply, nothing reveals the panel
