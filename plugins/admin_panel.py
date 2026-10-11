"""
Admin Panel  (ADMINS only)

  /panel  (or /admin)  -> colourful dashboard in private chat

Pages (all inline buttons, edited in place):
  📊 Stats        total users / groups / premium / banned / files, uptime, RAM, CPU
  🟢 Online       users active in the last 5 minutes (+ one-tap chat buttons)
  🕒 Recent       latest active users (+ one-tap chat buttons)
  📚 Commands     every admin command, grouped by category
  💬 Chat         open a two-way chat with any user (see admin_chat.py)
  🔌 Sessions     currently open chat sessions

Note on "online": Telegram never tells a bot whether a user is really online.
"Online" here means the user used the bot (message / button) in the last 5 minutes.
"""
import asyncio
import logging
import time
from datetime import datetime

import psutil
import pytz
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton as Btn, InlineKeyboardMarkup as Kb
from pyrogram.errors import MessageNotModified

from info import ADMINS
from database.users_chats_db import db
from database.ia_filterdb import Media, Media2
from info import MULTIPLE_DB

logger = logging.getLogger(__name__)
HTML = enums.ParseMode.HTML
START_TIME = time.time()
ONLINE_WINDOW = 300          # seconds a user counts as "online"
DB_WRITE_GAP = 60            # write last_seen to MongoDB at most once per user per minute
PAGE_SIZE = 8

# user_id -> last activity (epoch seconds), kept in memory for fast "online now"
LAST_SEEN: dict[int, float] = {}
_LAST_DB_WRITE: dict[int, float] = {}


# --------------------------------------------------------------------------- #
# Activity tracking (runs before everything else, never blocks other handlers) #
# --------------------------------------------------------------------------- #
async def _touch(user):
    if not user or user.is_bot:
        return
    now = time.time()
    LAST_SEEN[user.id] = now
    if now - _LAST_DB_WRITE.get(user.id, 0) < DB_WRITE_GAP:
        return
    _LAST_DB_WRITE[user.id] = now
    try:
        await db.col.update_one({"id": user.id}, {"$set": {"last_seen": int(now)}})
    except Exception:
        logger.exception("last_seen update failed")


@Client.on_message(filters.incoming & ~filters.service, group=-5)
async def _track_message(bot, message):
    await _touch(message.from_user)


@Client.on_callback_query(group=-5)
async def _track_callback(bot, query):
    await _touch(query.from_user)


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def _uptime() -> str:
    s = int(time.time() - START_TIME)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{d}d {h}h {m}m {s}s"


def _ago(ts: float) -> str:
    diff = int(time.time() - ts)
    if diff < 60:
        return f"{diff}s ago"
    if diff < 3600:
        return f"{diff // 60}m ago"
    if diff < 86400:
        return f"{diff // 3600}h ago"
    return f"{diff // 86400}d ago"


def _online_ids() -> list[int]:
    cutoff = time.time() - ONLINE_WINDOW
    ids = [uid for uid, ts in LAST_SEEN.items() if ts >= cutoff and uid not in ADMINS]
    return sorted(ids, key=lambda u: LAST_SEEN[u], reverse=True)


async def _safe(coro, default=0):
    try:
        return await coro
    except Exception:
        logger.exception("panel stat failed")
        return default


def _home_kb():
    return Kb([
        [Btn("📊 sᴛᴀᴛs", callback_data="ap_stats"), Btn("🟢 ᴏɴʟɪɴᴇ", callback_data="ap_online_0")],
        [Btn("🕒 ʀᴇᴄᴇɴᴛ ᴜsᴇʀs", callback_data="ap_recent_0"), Btn("📚 ᴄᴏᴍᴍᴀɴᴅs", callback_data="ap_cmds")],
        [Btn("💬 ᴄʜᴀᴛ ᴡɪᴛʜ ᴜsᴇʀ", callback_data="ap_chat"), Btn("🔌 sᴇssɪᴏɴs", callback_data="ap_sessions")],
        [Btn("🔄 ʀᴇꜰʀᴇsʜ", callback_data="ap_home"), Btn("❌ ᴄʟᴏsᴇ", callback_data="ap_close")],
    ])


def _back_kb(extra=None):
    rows = list(extra or [])
    rows.append([Btn("⬅️ ʙᴀᴄᴋ", callback_data="ap_home"), Btn("❌ ᴄʟᴏsᴇ", callback_data="ap_close")])
    return Kb(rows)


async def _edit(query, text, kb):
    try:
        await query.message.edit_text(text, reply_markup=kb, parse_mode=HTML,
                                      disable_web_page_preview=True)
    except MessageNotModified:
        pass


async def _name_of(bot, uid: int) -> str:
    doc = await db.col.find_one({"id": uid}, {"name": 1})
    name = (doc or {}).get("name")
    if not name:
        try:
            u = await bot.get_users(uid)
            name = u.first_name
        except Exception:
            name = "User"
    return name[:20]


# --------------------------------------------------------------------------- #
# Home                                                                         #
# --------------------------------------------------------------------------- #
async def _home_text() -> str:
    total = await _safe(db.total_users_count())
    online = len(_online_ids())
    return (
        "<b>👑 ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ 👑</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━</b>\n"
        f"👥 <b>ᴛᴏᴛᴀʟ ᴜsᴇʀs:</b> <code>{total}</code>\n"
        f"🟢 <b>ᴏɴʟɪɴᴇ ɴᴏᴡ:</b> <code>{online}</code>\n"
        f"⏱ <b>ᴜᴘᴛɪᴍᴇ:</b> <code>{_uptime()}</code>\n"
        "<b>━━━━━━━━━━━━━━━━━━</b>\n"
        "<i>👇 ᴄʜᴏᴏsᴇ ᴀɴ ᴏᴘᴛɪᴏɴ</i>"
    )


@Client.on_message(filters.private & filters.command(["panel", "admin"]) & filters.user(ADMINS))
async def open_panel(bot, message):
    await message.reply_text(await _home_text(), reply_markup=_home_kb(), parse_mode=HTML)


@Client.on_callback_query(filters.regex(r"^ap_home$") & filters.user(ADMINS))
async def cb_home(bot, query):
    await _edit(query, await _home_text(), _home_kb())
    await query.answer()


@Client.on_callback_query(filters.regex(r"^ap_close$") & filters.user(ADMINS))
async def cb_close(bot, query):
    await query.answer()
    try:
        await query.message.delete()
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Stats                                                                        #
# --------------------------------------------------------------------------- #
@Client.on_callback_query(filters.regex(r"^ap_stats$") & filters.user(ADMINS))
async def cb_stats(bot, query):
    await query.answer("Loading...")
    now = int(time.time())
    total = await _safe(db.total_users_count())
    chats = await _safe(db.total_chat_count())
    premium = await _safe(db.all_premium_users())
    banned_u = await _safe(db.col.count_documents({"ban_status.is_banned": True}))
    banned_c = await _safe(db.grp.count_documents({"chat_status.is_disabled": True}))
    act24 = await _safe(db.col.count_documents({"last_seen": {"$gte": now - 86400}}))
    act7 = await _safe(db.col.count_documents({"last_seen": {"$gte": now - 7 * 86400}}))
    files = await _safe(Media.count_documents())
    if MULTIPLE_DB:
        files += await _safe(Media2.count_documents())
    ram = psutil.virtual_memory().percent
    cpu = psutil.cpu_percent()
    ist = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%d %b %Y, %I:%M %p")

    text = (
        "<b>📊 ʙᴏᴛ sᴛᴀᴛɪsᴛɪᴄs</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━</b>\n"
        f"👥 <b>ᴛᴏᴛᴀʟ ᴜsᴇʀs:</b> <code>{total}</code>\n"
        f"🟢 <b>ᴏɴʟɪɴᴇ (5 ᴍɪɴ):</b> <code>{len(_online_ids())}</code>\n"
        f"📅 <b>ᴀᴄᴛɪᴠᴇ 24ʜ:</b> <code>{act24}</code>\n"
        f"🗓 <b>ᴀᴄᴛɪᴠᴇ 7ᴅ:</b> <code>{act7}</code>\n"
        f"💬 <b>ɢʀᴏᴜᴘs:</b> <code>{chats}</code>\n"
        f"💎 <b>ᴘʀᴇᴍɪᴜᴍ ᴜsᴇʀs:</b> <code>{premium}</code>\n"
        f"🚫 <b>ʙᴀɴɴᴇᴅ ᴜsᴇʀs:</b> <code>{banned_u}</code>\n"
        f"⛔ <b>ᴅɪsᴀʙʟᴇᴅ ɢʀᴏᴜᴘs:</b> <code>{banned_c}</code>\n"
        f"📁 <b>ꜰɪʟᴇs ɪɴ ᴅʙ:</b> <code>{files}</code>\n"
        "<b>━━━━━━━━━━━━━━━━━━</b>\n"
        f"⏱ <b>ᴜᴘᴛɪᴍᴇ:</b> <code>{_uptime()}</code>\n"
        f"🧠 <b>ʀᴀᴍ:</b> <code>{ram}%</code>   ⚙️ <b>ᴄᴘᴜ:</b> <code>{cpu}%</code>\n"
        f"🕐 <b>ᴛɪᴍᴇ (ɪsᴛ):</b> <code>{ist}</code>\n\n"
        "<i>ℹ️ Active/online counts start filling after this update goes live.</i>"
    )
    await _edit(query, text, _back_kb([[Btn("🔄 ʀᴇꜰʀᴇsʜ", callback_data="ap_stats")]]))


# --------------------------------------------------------------------------- #
# Online / recent users (paged, each row has a 💬 chat button)                 #
# --------------------------------------------------------------------------- #
async def _user_page(bot, query, ids_with_ts, page, kind, title):
    total = len(ids_with_ts)
    pages = max(1, -(-total // PAGE_SIZE))
    page = max(0, min(page, pages - 1))
    chunk = ids_with_ts[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]

    lines, rows = [], []
    for uid, ts in chunk:
        name = await _name_of(bot, uid)
        lines.append(f"• <a href='tg://user?id={uid}'>{name}</a> — <code>{uid}</code> — <i>{_ago(ts)}</i>")
        rows.append([Btn(f"💬 {name}", callback_data=f"adminchat_open_{uid}")])

    nav = []
    if page > 0:
        nav.append(Btn("◀️", callback_data=f"ap_{kind}_{page - 1}"))
    nav.append(Btn(f"{page + 1}/{pages}", callback_data="ap_noop"))
    if page < pages - 1:
        nav.append(Btn("▶️", callback_data=f"ap_{kind}_{page + 1}"))
    rows.append(nav)
    rows.append([Btn("🔄 ʀᴇꜰʀᴇsʜ", callback_data=f"ap_{kind}_{page}")])

    body = "\n".join(lines) if lines else "<i>No users yet.</i>"
    text = f"<b>{title}</b>  (<code>{total}</code>)\n<b>━━━━━━━━━━━━━━━━━━</b>\n{body}"
    await _edit(query, text, _back_kb(rows))


@Client.on_callback_query(filters.regex(r"^ap_online_(\d+)$") & filters.user(ADMINS))
async def cb_online(bot, query):
    await query.answer()
    page = int(query.matches[0].group(1))
    data = [(uid, LAST_SEEN[uid]) for uid in _online_ids()]
    await _user_page(bot, query, data, page, "online", "🟢 ᴏɴʟɪɴᴇ ɴᴏᴡ (ʟᴀsᴛ 5 ᴍɪɴ)")


@Client.on_callback_query(filters.regex(r"^ap_recent_(\d+)$") & filters.user(ADMINS))
async def cb_recent(bot, query):
    await query.answer()
    page = int(query.matches[0].group(1))
    data = []
    try:
        cur = db.col.find({"last_seen": {"$exists": True}}, {"id": 1, "last_seen": 1}) \
            .sort("last_seen", -1).limit(200)
        async for u in cur:
            if u["id"] not in ADMINS:
                data.append((u["id"], u["last_seen"]))
    except Exception:
        logger.exception("recent users failed")
    await _user_page(bot, query, data, page, "recent", "🕒 ʀᴇᴄᴇɴᴛ ᴜsᴇʀs")


@Client.on_callback_query(filters.regex(r"^ap_noop$") & filters.user(ADMINS))
async def cb_noop(bot, query):
    await query.answer()


# --------------------------------------------------------------------------- #
# Commands (grouped)                                                           #
# --------------------------------------------------------------------------- #
COMMANDS = {
    "👥 ᴜsᴇʀs": [
        ("/users", "list all users"), ("/ban <id> [reason]", "ban a user"),
        ("/unban <id>", "unban a user"), ("/send <id>", "send a message to one user"),
        ("/broadcast", "reply to a message -> send to all users"),
        ("/msg <id> <text>", "one-off message to a user"),
        ("/msg all <text>", "message every user"),
        ("/clear_junk", "remove blocked / deleted users"),
    ],
    "💬 ᴄʜᴀᴛ": [
        ("/chat <id>", "open two-way chat with a user"),
        ("/endchat", "close the current chat"),
        ("/panel", "open this panel"),
        ("(users) /contact", "users write to the admin"),
    ],
    "💎 ᴘʀᴇᴍɪᴜᴍ": [
        ("/add_premium <id> <time>", "give premium"), ("/remove_premium <id>", "remove premium"),
        ("/premium_users", "list premium users"), ("/get_premium <id>", "premium info"),
        ("/add_redeem", "create redeem code"), ("/trial_reset", "reset free trial"),
    ],
    "🗂 ꜰɪʟᴇs": [
        ("/delete", "delete a file (reply)"), ("/deleteall", "delete files by keyword"),
        ("/deletefiles", "delete CamRip / PreDVD files"), ("/setskip", "set index skip"),
        ("/movie_update", "movie update on/off"), ("/pm_search", "PM search on/off"),
        ("/del_msg", "clear filename notifications"),
    ],
    "🏘 ɢʀᴏᴜᴘs": [
        ("/chats", "list groups"), ("/leave <id>", "leave a group"),
        ("/disable <id>", "disable a group"), ("/enable <id>", "re-enable a group"),
        ("/invite <id>", "invite link of a group"), ("/grp_broadcast", "reply -> send to all groups"),
        ("/junk_group", "clear dead groups"), ("/resetallgroup", "reset all group settings"),
    ],
    "⚙️ sʏsᴛᴇᴍ": [
        ("/stats", "bot statistics"), ("/logs", "recent errors"),
        ("/restart", "restart the bot"), ("/commands", "update bot command menu"),
        ("/admin_cmd", "old admin command list"), ("/verify", "verification on/off (group)"),
        ("/system", "server info"), ("/ping", "latency"),
    ],
}
_CAT_KEYS = list(COMMANDS)


@Client.on_callback_query(filters.regex(r"^ap_cmds$") & filters.user(ADMINS))
async def cb_cmds(bot, query):
    await query.answer()
    rows = []
    for i in range(0, len(_CAT_KEYS), 2):
        rows.append([Btn(k, callback_data=f"ap_cat_{_CAT_KEYS.index(k)}") for k in _CAT_KEYS[i:i + 2]])
    text = ("<b>📚 ᴀʟʟ ᴀᴅᴍɪɴ ᴄᴏᴍᴍᴀɴᴅs</b>\n<b>━━━━━━━━━━━━━━━━━━</b>\n"
            "<i>Pick a category 👇</i>")
    await _edit(query, text, _back_kb(rows))


@Client.on_callback_query(filters.regex(r"^ap_cat_(\d+)$") & filters.user(ADMINS))
async def cb_cat(bot, query):
    await query.answer()
    idx = int(query.matches[0].group(1))
    if idx >= len(_CAT_KEYS):
        return
    key = _CAT_KEYS[idx]
    lines = [f"• <code>{c}</code> — {d}" for c, d in COMMANDS[key]]
    text = f"<b>{key}</b>\n<b>━━━━━━━━━━━━━━━━━━</b>\n" + "\n".join(lines)
    await _edit(query, text, Kb([[Btn("⬅️ ᴄᴀᴛᴇɢᴏʀɪᴇs", callback_data="ap_cmds"),
                                  Btn("🏠 ʜᴏᴍᴇ", callback_data="ap_home")]]))
