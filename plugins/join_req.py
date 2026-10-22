#Join Telegram Channel - @DREAMXBOTZ

from pyrogram import Client, filters, enums
from pyrogram.types import ChatJoinRequest
from database.users_chats_db import db
from info import ADMINS, AUTH_REQ_CHANNELS, AUTH_CHANNELS
from utils import fsub_status
from pyrogram.filters import create

def is_auth_req_channel(_, __, update):
    return update.chat.id in AUTH_REQ_CHANNELS

@Client.on_chat_join_request(create(is_auth_req_channel))
async def join_reqs(client, message: ChatJoinRequest):
    await db.add_join_req(message.from_user.id, message.chat.id)


@Client.on_message(filters.command("delreq") & filters.private & filters.user(ADMINS))
async def del_requests(client, message):
    await db.del_join_req()    
    await message.reply("<b>⚙ ꜱᴜᴄᴄᴇꜱꜱғᴜʟʟʏ ᴄʜᴀɴɴᴇʟ ʟᴇғᴛ ᴜꜱᴇʀꜱ ᴅᴇʟᴇᴛᴇᴅ</b>")


@Client.on_message(filters.command("fsub_status") & filters.private & filters.user(ADMINS))
async def fsub_status_cmd(client, message):
    """Shows which force-sub channels the bot can really check."""
    if not AUTH_CHANNELS and not AUTH_REQ_CHANNELS:
        return await message.reply("<b>No force-sub channel set. Put the ids in FSUB_CHANNEL_1 / FSUB_CHANNEL_2 (or AUTH_CHANNELS).</b>")
    wait = await message.reply("<b>Checking force-sub channels...</b>")
    lines = ["<b>Force-sub channels</b>"]
    lines += await fsub_status(client, AUTH_CHANNELS)
    if AUTH_REQ_CHANNELS:
        lines.append("\n<b>Request-to-join channels</b>")
        lines += await fsub_status(client, AUTH_REQ_CHANNELS, request=True)
    await wait.edit("\n".join(lines))
