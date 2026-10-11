"""
Feature gate  (runs before every other handler, group=-3)

When the admin switches a feature OFF in /panel -> Features, this plugin makes
sure normal users cannot reach it:

  * commands / deep links  -> short "disabled by admin" notice
  * inline buttons         -> alert popup
  * group searches         -> silently ignored (no spam in groups)
  * Maintenance Mode       -> the whole bot is paused for non-admins

Admins are never blocked.  Features that are switched inside other code
(stream, verification, force-sub, reactions ...) are read there with
feature_flags.is_on(...), this file only handles the "entry points".
"""
import asyncio
import logging
import re
import time

from pyrogram import Client, filters, enums

import feature_flags as ff
from info import ADMINS

logger = logging.getLogger(__name__)
HTML = enums.ParseMode.HTML

# /command  ->  feature key
CMD_FEATURES = {
    "plan": "premium", "myplan": "premium",
    "redeem": "redeem",
    "trendlist": "trending", "top_search": "trending",
    "imdb": "imdb_cmd", "search": "imdb_cmd",
    "id": "id_info", "info": "id_info",
    "font": "font_tool",
    "img": "telegraph_tool", "cup": "telegraph_tool", "telegraph": "telegraph_tool",
    "movies": "movies_series", "series": "movies_series",
    "contact": "contact_admin",
    "request": "request",
    "refer": "referral", "invitefriends": "referral",
}

# inline-button callback_data (regex)  ->  feature key
CB_FEATURES = [
    (re.compile(r"^topsearch$"), "trending"),
    (re.compile(r"^(premium_info|buy_info|upi_info|star_info)$|^buy_\d+"), "premium"),
    (re.compile(r"^(reffff|ref_point|invite_)"), "referral"),
    (re.compile(r"^give_trial$"), "free_trial"),
    (re.compile(r"^contact_admin_btn$"), "contact_admin"),
    (re.compile(r"^sendfiles"), "sendall"),
    (re.compile(r"^generate_stream_link"), "stream"),
    (re.compile(r"^imdb"), "imdb_cmd"),
    (re.compile(r"^(nxt|style)"), "font_tool"),
]

OFF_TEXT = "<b>🚫 ᴛʜɪs ꜰᴇᴀᴛᴜʀᴇ ɪs ᴛᴇᴍᴘᴏʀᴀʀɪʟʏ ᴅɪsᴀʙʟᴇᴅ ʙʏ ᴛʜᴇ ᴀᴅᴍɪɴ.</b>\n<i>Please try again later.</i>"
MAINT_TEXT = ("<b>🛠 ʙᴏᴛ ɪs ᴜɴᴅᴇʀ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ</b>\n\n"
              "<i>We are improving things. Please come back in a little while 🙏</i>")
MAINT_ALERT = "🛠 Bot is under maintenance. Please try again later."
OFF_ALERT = "🚫 This feature is temporarily disabled by the admin."

_LAST_NOTICE: dict[int, float] = {}      # user_id -> last time we replied (avoid spamming)


async def _delete_later(msg, secs=8):
    await asyncio.sleep(secs)
    try:
        await msg.delete()
    except Exception:
        pass


def _start_feature(text: str):
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return None
    payload = parts[1].strip()
    # reff_<id> is NOT gated here: with Invite & Earn off, the user still gets the normal welcome menu
    if payload.startswith(("allfiles", "sendall")):
        return "sendall"
    if payload == "premium":
        return "premium"
    return None


@Client.on_message(filters.incoming & ~filters.service & (filters.private | filters.group), group=-3)
async def message_gate(bot, message):
    user = message.from_user
    if not user or user.id in ADMINS:
        return
    await ff.ensure_loaded()

    text = (message.text or message.caption or "").strip()
    is_cmd = text.startswith("/")
    private = message.chat.type == enums.ChatType.PRIVATE

    feature = None
    if is_cmd:
        cmd = text.split(maxsplit=1)[0][1:].split("@")[0].lower()
        feature = _start_feature(text) if cmd == "start" else CMD_FEATURES.get(cmd)
    elif not private and message.text:
        feature = "request" if "#request" in text.lower() else "group_search"

    # ---- maintenance mode: everything is paused for normal users ----
    if ff.is_on("maintenance"):
        if private or is_cmd:
            now = time.time()
            if now - _LAST_NOTICE.get(user.id, 0) > 20:
                _LAST_NOTICE[user.id] = now
                try:
                    sent = await message.reply_text(MAINT_TEXT, parse_mode=HTML)
                    if not private:
                        asyncio.create_task(_delete_later(sent))
                except Exception:
                    pass
        message.stop_propagation()
        return

    if feature and not ff.is_on(feature):
        if feature != "group_search" and (private or is_cmd):
            now = time.time()
            if now - _LAST_NOTICE.get(user.id, 0) > 5:
                _LAST_NOTICE[user.id] = now
                try:
                    sent = await message.reply_text(OFF_TEXT, parse_mode=HTML)
                    if not private:
                        asyncio.create_task(_delete_later(sent))
                except Exception:
                    pass
        message.stop_propagation()


@Client.on_callback_query(group=-3)
async def callback_gate(bot, query):
    if not query.from_user or query.from_user.id in ADMINS:
        return
    await ff.ensure_loaded()

    if ff.is_on("maintenance"):
        await query.answer(MAINT_ALERT, show_alert=True)
        query.stop_propagation()
        return

    data = query.data or ""
    for pattern, feature in CB_FEATURES:
        if pattern.search(data):
            if not ff.is_on(feature):
                await query.answer(OFF_ALERT, show_alert=True)
                query.stop_propagation()
            return
