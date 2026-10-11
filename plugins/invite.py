"""
Invite & Earn  (user side)

  /refer  (or /invitefriends)   -> personal invite link, points, progress
  🎁 button on the start menu   -> same page
  🏆 Top inviters               -> leaderboard

The invite itself is registered in commands.py (/start reff_<id>) through
invite_system.register_invite().
"""
from pyrogram import Client, filters, enums

import invite_system


@Client.on_message(filters.private & filters.command(["refer", "invitefriends"]))
async def refer_cmd(bot, message):
    text, kb = await invite_system.invite_page(bot, message.from_user)
    await message.reply_text(text, reply_markup=kb, parse_mode=enums.ParseMode.HTML,
                             disable_web_page_preview=True)


@Client.on_callback_query(filters.regex(r"^invite_menu$"))
async def invite_menu_cb(bot, query):
    text, kb = await invite_system.invite_page(bot, query.from_user)
    await invite_system.edit_or_reply(query, text, kb)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^invite_top$"))
async def invite_top_cb(bot, query):
    text, kb = await invite_system.leaderboard_page()
    await invite_system.edit_or_reply(query, text, kb)
    await query.answer()
