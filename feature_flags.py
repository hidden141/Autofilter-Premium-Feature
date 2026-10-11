"""
Central feature switchboard.

Every feature the admin can turn ON/OFF from the panel (/panel -> Features) is
registered in FEATURES below.  The state is stored in MongoDB (bot_settings
collection, document _id="feature_flags") and cached in memory, so checking a
flag with `is_on("key")` is instant and synchronous.

Defaults come from info.py / environment variables, so the bot behaves exactly
as before until the admin flips something.

Numeric settings (e.g. invite points) live in the same document under "cfg".
"""
import logging

import info

logger = logging.getLogger(__name__)

DOC_ID = "feature_flags"

# --------------------------------------------------------------------------- #
# Registry                                                                     #
# key, category, label, default, description                                   #
# --------------------------------------------------------------------------- #
CATEGORIES = {
    "users":  "👥 ᴜsᴇʀ ꜰᴇᴀᴛᴜʀᴇs",
    "access": "💎 ᴘʀᴇᴍɪᴜᴍ & ᴀᴄᴄᴇss",
    "search": "🔍 sᴇᴀʀᴄʜ & ꜰɪʟᴇs",
    "tools":  "🧰 ᴛᴏᴏʟs",
    "system": "⚙️ sʏsᴛᴇᴍ",
}

FEATURES = [
    # ---- users
    ("pm_search",     "users",  "PM Search",              info.PM_SEARCH,        "Users can search movies in the bot's private chat"),
    ("group_search",  "users",  "Group Auto-Filter",      True,                  "Bot answers searches inside groups"),
    ("referral",      "users",  "Invite & Earn",          True,                  "Invite links, points and free premium rewards"),
    ("contact_admin", "users",  "Contact Admin",          True,                  "Users can message the admin through the bot"),
    ("request",       "users",  "Movie Requests",         True,                  "/request and #request in groups"),
    ("movies_series", "users",  "/movies & /series",      True,                  "Latest uploads lists"),
    ("reactions",     "users",  "Emoji Reactions",        info.EMOJI_MODE,       "Bot reacts to messages with emojis"),
    # ---- access
    ("premium",       "access", "Premium (/plan, buy)",   True,                  "Premium plans, /myplan and purchase buttons"),
    ("redeem",        "access", "Redeem Codes",           True,                  "/redeem command"),
    ("free_trial",    "access", "Free Trial",             True,                  "5-minute free premium trial button"),
    ("verify",        "access", "Verification (shortlink)", info.IS_VERIFY,      "Shortlink verification before files"),
    ("free_files",    "access", "Free Files Before Verify", True,                "Free files each day before verification starts"),
    ("daily_limit",   "access", "Daily File Limit",       True,                  "Daily file cap for non-premium users"),
    ("force_sub",     "access", "Force Subscribe",        True,                  "Users must join channels before getting files"),
    ("sendall",       "access", "Send All Button",        True,                  "'Send All' files button"),
    ("sendall_premium_only", "access", "Send All = Premium only", info.SENDALL_PREMIUM_ONLY, "Only premium users can use Send All"),
    ("trending",      "access", "Trending / Top Search",  True,                  "Trending list, top search"),
    ("trending_premium_only", "access", "Trending = Premium only", info.TRENDING_PREMIUM_ONLY, "Only premium users can see trending"),
    ("stream",        "access", "Stream / Fast Download", info.STREAM_MODE,      "Stream & fast-download buttons"),
    ("stream_premium_only", "access", "Stream = Premium only", info.PREMIUM_STREAM_MODE, "Only premium users can use stream"),
    # ---- search
    ("spell_check",   "search", "Spell Check Suggestions", True,                 "Suggest names when a search has no result (global override)"),
    ("imdb_results",  "search", "IMDb Result Cards",      True,                  "Show IMDb details with results (global override)"),
    ("auto_delete",   "search", "Auto-Delete Results",    True,                  "Delete result messages after a while (global override)"),
    ("imdb_cmd",      "search", "/imdb & /search",        True,                  "IMDb info commands"),
    # ---- tools
    ("id_info",       "tools",  "/id & /info",            True,                  "Telegram ID / user info commands"),
    ("font_tool",     "tools",  "Font Generator",         True,                  "/font command"),
    ("telegraph_tool", "tools", "Telegraph Upload",       True,                  "/img /cup /telegraph"),
    # ---- system
    ("movie_update",  "system", "Movie Update Posts",     info.MOVIE_UPDATE_NOTIFICATION, "Auto notification posts when files are indexed"),
    ("auto_index",    "system", "Auto-Index Channels",    True,                  "Save files posted in the index channels"),
]

KEYS = [f[0] for f in FEATURES]
DEFAULTS = {f[0]: bool(f[3]) for f in FEATURES}
DEFAULTS["maintenance"] = False          # master switch (not in the list above, has its own panel button)
LABELS = {f[0]: f[2] for f in FEATURES}
LABELS["maintenance"] = "Maintenance Mode"

# numeric settings: key -> (default, min, max, step, label)
CFG_DEFAULTS = {
    "invite_points": (10, 1, 1000, 5, "Points per invite"),
    "invite_target": (100, 10, 10000, 10, "Points needed for reward"),
    "invite_days":   (30, 1, 365, 1, "Premium days as reward"),
}

_FLAGS: dict[str, bool] = {}
_CFG: dict[str, int] = {}
_loaded = False


def _col():
    from database.users_chats_db import db   # lazy: users_chats_db imports this module lazily too
    return db.botcol


async def load():
    """Load switches from MongoDB (safe to call many times)."""
    global _loaded
    try:
        doc = await _col().find_one({"_id": DOC_ID}) or {}
        _FLAGS.clear()
        _FLAGS.update({k: bool(v) for k, v in (doc.get("flags") or {}).items()})
        _CFG.clear()
        _CFG.update({k: int(v) for k, v in (doc.get("cfg") or {}).items()})
        # one-time migration of the old /pm_search and /movie_update settings
        legacy_map = {"pm_search": "PM_SEARCH", "movie_update": "MOVIE_UPDATE_NOTIFICATION"}
        for key, old in legacy_map.items():
            if key not in _FLAGS:
                legacy = await _col().find_one({old: {"$exists": True}}, {old: 1})
                if legacy is not None:
                    _FLAGS[key] = bool(legacy[old])
        _loaded = True
    except Exception:
        logger.exception("feature flags load failed - using defaults")
        _loaded = True


async def ensure_loaded():
    if not _loaded:
        await load()


def is_on(key: str) -> bool:
    if key in _FLAGS:
        return _FLAGS[key]
    return DEFAULTS.get(key, True)


async def set_flag(key: str, value: bool):
    if key not in DEFAULTS:
        raise KeyError(key)
    _FLAGS[key] = bool(value)
    await _col().update_one({"_id": DOC_ID}, {"$set": {f"flags.{key}": bool(value)}}, upsert=True)


async def toggle(key: str) -> bool:
    new = not is_on(key)
    await set_flag(key, new)
    return new


def get_cfg(key: str) -> int:
    return int(_CFG.get(key, CFG_DEFAULTS[key][0]))


async def adjust_cfg(key: str, direction: int) -> int:
    default, lo, hi, step, _ = CFG_DEFAULTS[key]
    value = max(lo, min(hi, get_cfg(key) + direction * step))
    _CFG[key] = value
    await _col().update_one({"_id": DOC_ID}, {"$set": {f"cfg.{key}": value}}, upsert=True)
    return value


# ----- helpers for the panel ------------------------------------------------ #
def by_category(cat: str):
    return [(i, f) for i, f in enumerate(FEATURES) if f[1] == cat]


def category_counts(cat: str):
    items = by_category(cat)
    on = sum(1 for _, f in items if is_on(f[0]))
    return on, len(items)


async def set_category(cat: str, value: bool):
    for _, f in by_category(cat):
        await set_flag(f[0], value)
