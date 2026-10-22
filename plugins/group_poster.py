import os
import asyncio
import logging
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, ChatAdminRequired
from info import ADMINS
from database.users_chats_db import db

logger = logging.getLogger(__name__)

# All links can be changed from Render environment variables if needed
LINKS = {
    "main":         os.environ.get("POSTER_MAIN_CHANNEL",   "https://t.me/roaroic0"),
    "updates":      os.environ.get("POSTER_UPDATE_CHANNEL", "https://t.me/roaroic1"),
    "bot":          os.environ.get("POSTER_SEARCH_BOT",     "https://t.me/roaroic_bot"),
    "movies_group": os.environ.get("POSTER_MOVIES_GROUP",   "https://t.me/roaroicgroup"),
    "discussion":   os.environ.get("POSTER_DISCUSSION",     "https://t.me/+HwZPzMx1njs2N2Y9"),
    "notify":       os.environ.get("POSTER_NOTIFY_CHANNEL", "https://t.me/+vNAhFBYrIQg5ZTk9"),
}

MESSAGE = """
<b>╔══════ •✦• ══════╗
          🎬  ʀᴏᴀʀᴏɪᴄ  🎬
╚══════ •✦• ══════╝</b>

<b>ᴍᴏᴠɪᴇs  •  sᴇʀɪᴇs  •  ᴇɴᴛᴇʀᴛᴀɪɴᴍᴇɴᴛ</b>

🔍 <b>अपनी मन पसंद movie का नाम</b>
<b>search करें और पाएं instantly!</b>

━━━━┈┉•✦•┉┈━━━━
⚡ <b>sᴇᴀʀᴄʜ  ➜  sᴇʟᴇᴄᴛ  ➜  ᴡᴀᴛᴄʜ</b>
━━━━┈┉•✦•┉┈━━━━

<blockquote>🆕 ʟᴀᴛᴇsᴛ ᴍᴏᴠɪᴇs ɪɴ 8-12 ʜᴏᴜʀs
🎥 ᴍᴜʟᴛɪᴘʟᴇ ǫᴜᴀʟɪᴛʏ ᴏᴘᴛɪᴏɴs
🌐 ʜɪɴᴅɪ &amp; ᴏᴛʜᴇʀ ʟᴀɴɢᴜᴀɢᴇs</blockquote>

👇 <b>ɴᴇᴇᴄʜᴇ ᴅɪᴇ ɢᴀʏᴇ ʙᴜᴛᴛᴏɴs sᴇ ᴊᴜᴅᴇɪɴ</b>
"""


def poster_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Search Movies Now", url=LINKS["bot"])],
        [InlineKeyboardButton("🎥 Main Channel", url=LINKS["main"]),
         InlineKeyboardButton("🆕 Update Movies", url=LINKS["updates"])],
        [InlineKeyboardButton("👥 Movies Group", url=LINKS["movies_group"]),
         InlineKeyboardButton("💬 Discussion", url=LINKS["discussion"])],
        [InlineKeyboardButton("🔔 Notification Channel", url=LINKS["notify"])],
    ])


_poster_msgs = {}   # chat_id -> poster message id (memory copy; DB copy is used when the group exists there)
PIN_HINT = ("📌 <b>Poster ko hamesha pin rakhne ke liye</b> bot ko admin banayein "
            "(<b>Pin Messages</b> permission ke saath).")


async def _get_saved_id(chat_id):
    if chat_id in _poster_msgs:
        return _poster_msgs[chat_id]
    try:
        doc = await db.grp.find_one({"id": int(chat_id)})
        return (doc or {}).get("poster_msg_id")
    except Exception:
        return None


async def _save_id(chat_id, msg_id):
    _poster_msgs[chat_id] = msg_id
    try:  # no upsert: never creates half-filled group documents
        await db.grp.update_one({"id": int(chat_id)}, {"$set": {"poster_msg_id": msg_id}})
    except Exception:
        pass


async def pin_poster(client, chat_id, msg_id):
    """Pins the poster silently and removes the 'bot pinned a message' notice. Returns True if pinned."""
    try:
        note = await client.pin_chat_message(chat_id, msg_id, disable_notification=True)
        try:
            if note is not None and not isinstance(note, bool):
                await note.delete()
        except Exception:
            pass
        return True
    except FloodWait:
        raise
    except Exception as e:  # not admin / no pin permission
        logger.info("Could not pin poster in %s: %s", chat_id, e)
        return False


async def _drop_hint(client, chat_id):
    try:
        hint = await client.send_message(chat_id, PIN_HINT, parse_mode=enums.ParseMode.HTML)
        await asyncio.sleep(60)
        await hint.delete()
    except Exception:
        pass


async def send_poster(client, chat_id, pin=True):
    """Text-only welcome poster with working link buttons, pinned permanently (no image)."""
    old_id = await _get_saved_id(chat_id)   # keep only ONE poster per group
    msg = await client.send_message(
        chat_id=chat_id,
        text=MESSAGE,
        reply_markup=poster_buttons(),
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=True,
    )
    await _save_id(chat_id, msg.id)
    if old_id and old_id != msg.id:
        try:
            await client.delete_messages(chat_id, old_id)
        except Exception:
            pass
    if pin and not await pin_poster(client, chat_id, msg.id):
        asyncio.create_task(_drop_hint(client, chat_id))
    return msg


@Client.on_message(filters.new_chat_members & filters.group, group=7)
async def poster_on_bot_added(client, message):
    try:
        me = await client.get_me()
        if not any(u.id == me.id for u in message.new_chat_members):
            return
        await send_poster(client, message.chat.id)
    except FloodWait as e:
        await asyncio.sleep(e.value)
        await send_poster(client, message.chat.id)
    except Exception as e:
        logger.warning("Poster send failed in %s: %s", message.chat.id, e)


@Client.on_chat_member_updated(filters.group, group=7)
async def poster_pin_when_promoted(client, update):
    """If the bot is made admin later, pin the poster that was posted when it joined."""
    try:
        new = update.new_chat_member
        if not new or not update.old_chat_member:
            return
        me = await client.get_me()
        if new.user.id != me.id:
            return
        was_admin = update.old_chat_member.status == enums.ChatMemberStatus.ADMINISTRATOR
        is_admin = new.status == enums.ChatMemberStatus.ADMINISTRATOR
        if not is_admin or was_admin:
            return
        msg_id = await _get_saved_id(update.chat.id)
        if msg_id:
            await pin_poster(client, update.chat.id, msg_id)
        else:
            await send_poster(client, update.chat.id)
    except FloodWait:
        pass
    except Exception as e:
        logger.warning("Pin on promotion failed in %s: %s", update.chat.id, e)


@Client.on_message(filters.command("poster") & filters.user(ADMINS))
async def poster_command(client, message):
    # In a group: (re)post + pin poster there. In bot PM: send poster to ALL groups bot is in.
    if message.chat.type.name in ("GROUP", "SUPERGROUP"):
        try:
            await send_poster(client, message.chat.id)
        except Exception as e:
            await message.reply_text(f"Poster send failed: {e}")
        return

    status = await message.reply_text("📢 Sending poster to all groups...")
    ok = failed = 0
    async for chat in await db.get_all_chats():
        chat_id = chat.get("id")
        if not chat_id or (chat.get("chat_status") or {}).get("is_disabled"):
            continue
        try:
            await send_poster(client, chat_id)
            ok += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
            try:
                await send_poster(client, chat_id)
                ok += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1
        await asyncio.sleep(1.5)
    await status.edit_text(f"✅ Poster sent: {ok} groups\n❌ Failed: {failed} groups")
