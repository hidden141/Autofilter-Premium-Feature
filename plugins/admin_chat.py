"""
Admin <-> User direct chat through the bot.

Admin commands (private chat with the bot, ADMINS only):
  /chat <user_id>        - open a live chat session with that user
  /endchat               - close the current session
  /msg <user_id> <text>  - send a one-off text message to a user
  /msg all <text>        - send a text message to ALL users (or reply to any message with /msg all)

While a session is open:
  * everything the admin sends (text, media, ...) is delivered to the user
  * everything the user sends is delivered to the admin
  * the user's normal bot features are paused, so the bot doesn't try to
    treat their chat messages as movie searches. Commands (/start, ...) still work.

Sessions are kept in memory and are cleared when the bot restarts.
"""
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.errors import (
    FloodWait, InputUserDeactivated, UserIsBlocked, PeerIdInvalid, UserNotParticipant
)
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from info import ADMINS
from database.users_chats_db import db

logger = logging.getLogger(__name__)

# admin_id -> user_id
ADMIN_SESSIONS: dict[int, int] = {}
# user_id -> set(admin_id)   (reverse index so user messages are routed fast)
USER_SESSIONS: dict[int, set[int]] = {}

# admins who pressed "Chat with user" in the panel and must now send a user id
WAITING_ID: set[int] = set()
# users who typed /contact and whose next message goes to the admins
PENDING_CONTACT: dict[int, float] = {}
CONTACT_COOLDOWN = 30  # seconds between /contact uses
_LAST_CONTACT: dict[int, float] = {}


async def _contact_enabled(bot) -> bool:
    return True

SEND_ERRORS = (UserIsBlocked, InputUserDeactivated, PeerIdInvalid)


def _end_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴇɴᴅ ᴄʜᴀᴛ", callback_data="adminchat_end")]])


def _open(admin_id: int, user_id: int):
    _close(admin_id)
    ADMIN_SESSIONS[admin_id] = user_id
    USER_SESSIONS.setdefault(user_id, set()).add(admin_id)


def _close(admin_id: int):
    user_id = ADMIN_SESSIONS.pop(admin_id, None)
    if user_id is not None:
        admins = USER_SESSIONS.get(user_id)
        if admins:
            admins.discard(admin_id)
            if not admins:
                USER_SESSIONS.pop(user_id, None)
    return user_id


def _user_label(user) -> str:
    name = " ".join(filter(None, [user.first_name, getattr(user, "last_name", None)])) or "User"
    uname = f" (@{user.username})" if getattr(user, "username", None) else ""
    return f"{name}{uname} [<code>{user.id}</code>]"


@Client.on_message(filters.private & filters.command("chat") & filters.user(ADMINS))
async def start_admin_chat(bot, message):
    if len(message.command) < 2 or not message.command[1].lstrip("-").isdigit():
        return await message.reply_text(
            "<b>Usage:</b> <code>/chat user_id</code>\n"
            "Send messages normally to talk to the user. Use /endchat to stop."
        )
    user_id = int(message.command[1])
    if not await db.is_user_exist(user_id):
        return await message.reply_text(
            "<b>⚠️ This user has not started the bot yet, so I can't message them.</b>"
        )
    try:
        user = await bot.get_users(user_id)
        label = _user_label(user)
    except Exception:
        label = f"[<code>{user_id}</code>]"

    _open(message.from_user.id, user_id)
    await message.reply_text(
        f"<b>💬 Chat opened with {label}.</b>\n\n"
        "Everything you send now goes to the user, and their replies come here.\n"
        "Use /endchat to stop.",
        reply_markup=_end_kb(),
    )


@Client.on_message(filters.private & filters.command("endchat") & filters.user(ADMINS))
async def end_admin_chat(bot, message):
    user_id = _close(message.from_user.id)
    if user_id is None:
        return await message.reply_text("<b>No active chat session.</b>")
    await message.reply_text(f"<b>✅ Chat with <code>{user_id}</code> closed.</b>")


@Client.on_callback_query(filters.regex(r"^adminchat_end$") & filters.user(ADMINS))
async def end_admin_chat_cb(bot, query):
    user_id = _close(query.from_user.id)
    await query.answer("Chat closed" if user_id else "No active chat", show_alert=False)
    if user_id:
        await query.message.reply_text(f"<b>✅ Chat with <code>{user_id}</code> closed.</b>")


_msg_all_lock = asyncio.Lock()


async def _msg_all(bot, message, text):
    """/msg all <text>  or  reply to a message with /msg all  -> send to every user."""
    src = message.reply_to_message
    if not src and not text:
        return await message.reply_text(
            "<b>Usage:</b> <code>/msg all your message</code>\n"
            "or reply to a message with <code>/msg all</code>"
        )
    if _msg_all_lock.locked():
        return await message.reply_text("<b>⚠️ Another /msg all is already running. Please wait.</b>")
    async with _msg_all_lock:
        status = await message.reply_text("<b>📤 Sending to all users...</b>")
        success = blocked = failed = 0
        try:
            async for user in await db.get_all_users():
                uid = int(user["id"])
                try:
                    try:
                        if src:
                            await src.copy(uid)
                        else:
                            await bot.send_message(uid, text)
                    except FloodWait as e:
                        await asyncio.sleep(e.value + 1)
                        if src:
                            await src.copy(uid)
                        else:
                            await bot.send_message(uid, text)
                    success += 1
                except SEND_ERRORS:
                    blocked += 1
                except Exception:
                    logger.exception("msg all failed for %s", uid)
                    failed += 1
                if (success + blocked + failed) % 25 == 0:
                    await asyncio.sleep(1)  # stay under Telegram rate limits
        except Exception:
            logger.exception("msg all aborted")
        await status.edit_text(
            "<b>✅ Message to all users finished.</b>\n\n"
            f"Delivered: <code>{success}</code>\n"
            f"Blocked/deleted: <code>{blocked}</code>\n"
            f"Failed: <code>{failed}</code>"
        )


@Client.on_message(filters.private & filters.command("msg") & filters.user(ADMINS))
async def one_off_message(bot, message):
    parts = message.text.split(None, 2)
    if len(parts) >= 2 and parts[1].lower() == "all":
        return await _msg_all(bot, message, parts[2] if len(parts) > 2 else None)
    if len(parts) < 3 or not parts[1].lstrip("-").isdigit():
        return await message.reply_text(
            "<b>Usage:</b>\n"
            "<code>/msg user_id your message</code>\n"
            "<code>/msg all your message</code> (send to every user)\n"
            "Or reply to any message with <code>/msg all</code> to send that message to everyone."
        )
    user_id, text = int(parts[1]), parts[2]
    if not await db.is_user_exist(user_id):
        return await message.reply_text(
            "<b>⚠️ This user has not started the bot yet.</b>"
        )
    try:
        await bot.send_message(user_id, text)
        await message.reply_text(f"<b>✅ Sent to <code>{user_id}</code>.</b>")
    except SEND_ERRORS as e:
        await message.reply_text("<b>❌ Could not deliver. The user may have blocked the bot.</b>")
    except Exception as e:
        logger.exception("admin /msg failed")
        await message.reply_text("<b>❌ Message could not be sent.</b>")


# group=-1 so these run before the regular private-message handlers (e.g. pm filter),
# and stop_propagation() keeps the chat messages from being treated as searches.
@Client.on_message(filters.private & filters.incoming & filters.user(ADMINS) & ~filters.command(
    ["chat", "endchat", "msg"]) & ~filters.regex(r"^/"), group=-1)
async def admin_to_user(bot, message):
    if message.from_user.id in WAITING_ID and message.text:
        WAITING_ID.discard(message.from_user.id)
        txt = message.text.strip()
        if txt.lstrip("-").isdigit():
            await _open_session(bot, message, message.from_user.id, int(txt))
        else:
            await message.reply_text("<b>⚠️ That is not a valid user id. Open the panel again with /panel.</b>")
        message.stop_propagation()
        return
    user_id = ADMIN_SESSIONS.get(message.from_user.id)
    if user_id is None:
        return  # no session: behave as normal
    try:
        await message.copy(user_id)
        try:
            await message.react("👍")
        except Exception:
            pass  # reaction is only a delivery tick; ignore failures
    except FloodWait as e:
        await message.reply_text("<b>⏳ Please wait a moment and try again.</b>")
    except SEND_ERRORS as e:
        _close(message.from_user.id)
        await message.reply_text(
            "<b>❌ User is unavailable (blocked the bot or deleted account). Chat closed.</b>"
        )
    except Exception as e:
        logger.exception("admin_to_user failed")
        await message.reply_text("<b>❌ Message could not be delivered.</b>")
    message.stop_propagation()


@Client.on_message(filters.private & filters.incoming & ~filters.user(ADMINS) & ~filters.regex(r"^/")
                   & ~filters.service, group=-1)
async def user_to_admin(bot, message):
    if not message.from_user:
        return
    uid = message.from_user.id
    if uid in PENDING_CONTACT:
        PENDING_CONTACT.pop(uid, None)
        delivered = 0
        header = (f"📩 <b>New message from {_user_label(message.from_user)}</b>\n"
                  "Tap below to open a live chat and reply.")
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("💬 ʀᴇᴘʟʏ / ᴏᴘᴇɴ ᴄʜᴀᴛ", callback_data=f"adminchat_open_{uid}")]])
        for admin_id in ADMINS:
            try:
                await message.copy(admin_id)
                await bot.send_message(admin_id, header, reply_markup=kb)
                delivered += 1
            except Exception:
                logger.exception("contact forward failed for admin %s", admin_id)
        await message.reply_text(
            "<b>✅ ʏᴏᴜʀ ᴍᴇssᴀɢᴇ ʜᴀs ʙᴇᴇɴ sᴇɴᴛ ᴛᴏ ᴛʜᴇ ᴀᴅᴍɪɴ.\nᴘʟᴇᴀsᴇ ᴡᴀɪᴛ ꜰᴏʀ ᴀ ʀᴇᴘʟʏ 💌</b>" if delivered
            else "<b>❌ Could not reach the admin right now. Please try again later.</b>"
        )
        message.stop_propagation()
        return
    admins = USER_SESSIONS.get(uid)
    if not admins:
        return  # not in a session: normal bot behaviour
    header = f"💬 <b>{_user_label(message.from_user)}</b>"
    for admin_id in list(admins):
        try:
            await bot.send_message(admin_id, header)
            await message.copy(admin_id)
        except Exception:
            logger.exception("user_to_admin failed for admin %s", admin_id)
    message.stop_propagation()


# --------------------------------------------------------------------------- #
# Panel buttons + /contact                                                     #
# --------------------------------------------------------------------------- #
async def _open_session(bot, message, admin_id: int, user_id: int):
    if not await db.is_user_exist(user_id):
        return await message.reply_text(
            "<b>⚠️ This user has not started the bot yet, so I can't message them.</b>")
    try:
        label = _user_label(await bot.get_users(user_id))
    except Exception:
        label = f"[<code>{user_id}</code>]"
    _open(admin_id, user_id)
    await message.reply_text(
        f"<b>💬 Chat opened with {label}.</b>\n\n"
        "Everything you send now goes to the user, and their replies come here.\n"
        "Use /endchat to stop.",
        reply_markup=_end_kb(),
    )
    try:
        await bot.send_message(user_id, "<b>💬 ᴀᴅᴍɪɴ ʜᴀs ᴊᴏɪɴᴇᴅ ᴛʜᴇ ᴄʜᴀᴛ. ʏᴏᴜ ᴄᴀɴ ʀᴇᴘʟʏ ʜᴇʀᴇ.</b>")
    except SEND_ERRORS:
        _close(admin_id)
        await message.reply_text("<b>❌ User is unavailable (blocked the bot). Chat closed.</b>")


@Client.on_callback_query(filters.regex(r"^adminchat_open_(-?\d+)$") & filters.user(ADMINS))
async def open_chat_cb(bot, query):
    await query.answer()
    await _open_session(bot, query.message, query.from_user.id, int(query.matches[0].group(1)))


@Client.on_callback_query(filters.regex(r"^ap_chat$") & filters.user(ADMINS))
async def ask_user_id_cb(bot, query):
    WAITING_ID.add(query.from_user.id)
    await query.answer()
    await query.message.reply_text(
        "<b>💬 Send the <u>user id</u> you want to chat with.</b>\n"
        "<i>Tip: use the 🟢 Online / 🕒 Recent pages to open a chat with one tap.</i>")


@Client.on_callback_query(filters.regex(r"^ap_sessions$") & filters.user(ADMINS))
async def sessions_cb(bot, query):
    await query.answer()
    if not ADMIN_SESSIONS:
        text = "<b>🔌 Active chats</b>\n\n<i>No open chat sessions.</i>"
    else:
        text = "<b>🔌 Active chats</b>\n\n" + "\n".join(
            f"• admin <code>{a}</code> ⇄ user <code>{u}</code>" for a, u in ADMIN_SESSIONS.items())
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data="ap_home")]])
    try:
        await query.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass


@Client.on_message(filters.private & filters.command("contact") & ~filters.user(ADMINS))
async def contact_admin(bot, message):
    if not await _contact_enabled(bot):
        return await message.reply_text("<b>⚠️ Contacting the admin is currently disabled.</b>")
    uid = message.from_user.id
    import time
    now = time.time()
    if now - _LAST_CONTACT.get(uid, 0) < CONTACT_COOLDOWN:
        return await message.reply_text("<b>⏳ Please wait a few seconds before using /contact again.</b>")
    _LAST_CONTACT[uid] = now
    PENDING_CONTACT[uid] = now
    await message.reply_text(
        "<b>📩 ᴡʀɪᴛᴇ ʏᴏᴜʀ ᴍᴇssᴀɢᴇ ɴᴏᴡ</b>\n\n"
        "Send ONE message (text, photo, video, file...) and it will reach the admin directly.\n"
        "Send any command (like /start) to cancel."
    )


@Client.on_message(filters.private & filters.incoming & ~filters.user(ADMINS) & filters.regex(r"^/")
                   & ~filters.command("contact"), group=-2)
async def cancel_contact(bot, message):
    if message.from_user:
        PENDING_CONTACT.pop(message.from_user.id, None)


@Client.on_callback_query(filters.regex(r"^contact_admin_btn$") & ~filters.user(ADMINS))
async def contact_admin_btn(bot, query):
    if not await _contact_enabled(bot):
        return await query.answer("Contacting the admin is currently disabled.", show_alert=True)
    import time
    uid = query.from_user.id
    now = time.time()
    if now - _LAST_CONTACT.get(uid, 0) < CONTACT_COOLDOWN:
        return await query.answer("Please wait a few seconds.", show_alert=True)
    _LAST_CONTACT[uid] = now
    PENDING_CONTACT[uid] = now
    await query.answer()
    await query.message.reply_text(
        "<b>📩 ᴡʀɪᴛᴇ ʏᴏᴜʀ ᴍᴇssᴀɢᴇ ɴᴏᴡ</b>\n\n"
        "Send ONE message (text, photo, video, file...) and it will reach the admin directly.\n"
        "Send any command (like /start) to cancel."
    )
