import re
import os
from os import environ, getenv
from Script import script

# Utility functions
id_pattern = re.compile(r'^.\d+$')

def is_enabled(value, default):
    value = str(value).strip().lower()
    if value in ["true", "yes", "1", "enable", "y", "on"]:
        return True
    elif value in ["false", "no", "0", "disable", "n", "off", ""]:
        return False
    else:
        return default

# ============================
# Bot Information Configuration
# ============================
SESSION = environ.get('SESSION', 'royal_search')   # Session name for the bot
API_ID = int(environ.get('API_ID', '')) # API ID from my.telegram.org
API_HASH = environ.get('API_HASH', '')  # API Hash from my.telegram.org
BOT_TOKEN = environ.get('BOT_TOKEN', "")    # Bot token from @BotFather

# ============================
# Bot Settings Configuration
# ============================
CACHE_TIME = int(environ.get('CACHE_TIME', 300))    # Cache time in seconds (default: 5 minutes)
USE_CAPTION_FILTER = is_enabled(str(environ.get('USE_CAPTION_FILTER', True)), True)  # Use caption filter for search results (default: True)
INDEX_CAPTION = is_enabled(str(environ.get('SAVE_CAPTION', True)), True) # Save caption db when idexing make it False if you dont use USE_CAPTION_FILTER for search results (default: True)
#Making it false will not save caption in db SO you can save some storage space


PICS = (environ.get('PICS', 'https://graph.org/file/56b5deb73f3b132e2bb73.jpg https://graph.org/file/5303692652d91d52180c2.jpg https://graph.org/file/425b6f46efc7c6d64105f.jpg https://graph.org/file/876867e761c6c7a29855b.jpg')).split()  # Sample pic
NOR_IMG = environ.get("NOR_IMG", "https://graph.org/file/e20b5fdaf217252964202.jpg")
MELCOW_PHOTO = environ.get("MELCOW_PHOTO", "https://graph.org/file/56b5deb73f3b132e2bb73.jpg")
SPELL_IMG = environ.get("SPELL_IMG", "https://graph.org/file/13702ae26fb05df52667c.jpg")
SUBSCRIPTION = (environ.get('SUBSCRIPTION', 'https://graph.org/file/242b7f1b52743938d81f1.jpg'))
FSUB_PICS = (environ.get('FSUB_PICS', 'https://graph.org/file/7478ff3eac37f4329c3d8.jpg https://graph.org/file/56b5deb73f3b132e2bb73.jpg')).split()  # Fsub pic

# ============================
# Admin, Channels & Users Configuration
# ============================
ADMINS = [int(admin) if id_pattern.search(admin) else admin for admin in environ.get('ADMINS', '').split()] # Replace with the actual admin ID(s) to add
CHANNELS = [int(ch) if id_pattern.search(ch) else ch for ch in environ.get('CHANNELS', '-1001553577227').split()]  # Channel id for auto indexing (make sure bot is admin)

LOG_CHANNEL = int(environ.get('LOG_CHANNEL', '-100'))  # Log channel id (make sure bot is admin)
BIN_CHANNEL = int(environ.get('BIN_CHANNEL', '-100'))  # Bin channel id (make sure bot is admin)
PREMIUM_LOGS = int(environ.get('PREMIUM_LOGS', '-1004379059015'))  # Premium logs channel id
DELETE_CHANNELS = [int(dch) if id_pattern.search(dch) else dch for dch in environ.get('DELETE_CHANNELS', '-100').split()] #(make sure bot is admin)
support_chat_id = environ.get('SUPPORT_CHAT_ID', '-5364188210')  # Support group id (make sure bot is admin)
reqst_channel = environ.get('REQST_CHANNEL_ID', '-100')  # Request channel id (make sure bot is admin)
SUPPORT_CHAT = environ.get('SUPPORT_CHAT', 'https://t.me/+cNr_1nOUfTdjYTdl')  # Support group link (make sure bot is admin)

# FORCE_SUB 
auth_req_channels = environ.get("AUTH_REQ_CHANNELS", "-100")# requst to join Channel for force sub (make sure bot is admin) only for bot ADMINS  
auth_channels     = environ.get("AUTH_CHANNELS", "-100")# Channels for force sub (make sure bot is admin)

# ============================
# Payment Configuration
# ============================
QR_CODE = environ.get('QR_CODE', 'Your_Qr_Code')    # QR code image for payments
OWNER_UPI_ID = environ.get('OWNER_UPI_ID', 'ɴᴏ ᴀᴠᴀɪʟᴀʙʟᴇ ʀɪɢʜᴛ ɴᴏᴡ')    # Owner UPI ID for payments

STAR_PREMIUM_PLANS = {
    10: "7day",
    20: "15day",    
    40: "1month", 
    55: "45day",
    75: "60day",
}  # Premium plans with their respective durations in days

# ============================
# MongoDB Configuration
# ============================
DATABASE_URI = environ.get('DATABASE_URI', "")  # MongoDB URI for the database
DATABASE_NAME = environ.get('DATABASE_NAME', "Cluster0") # Database name (default: cluster)
COLLECTION_NAME = environ.get('COLLECTION_NAME', 'royal_files') # Collection name (default: dreamcinezone_files)

# If MULTIPLE_DB Is True Then Fill DATABASE_URI2 Value Else You Will Get Error.
MULTIPLE_DB = is_enabled(os.environ.get('MULTIPLE_DB', "False"), False) # Type True For Turn On MULTIPLE DB FUNTION 
DATABASE_URI2 = environ.get('DATABASE_URI2', "")  # MongoDB URI for the second database (if MULTIPLE_DB is True)
# ============================
# Movie Notification & Update Settings
# ============================
MOVIE_UPDATE_NOTIFICATION = is_enabled(str(environ.get('MOVIE_UPDATE_NOTIFICATION', True)), True)  # Notification On (True) / Off (False)
MOVIE_UPDATE_CHANNEL = int(environ.get('MOVIE_UPDATE_CHANNEL', '-1003900854538'))  # Notification of sent to your channel
DREAMXBOTZ_IMAGE_FETCH = is_enabled(str(environ.get('DREAMXBOTZ_IMAGE_FETCH', True)), True)  # On (True) / Off (False)
LINK_PREVIEW = is_enabled(str(environ.get('LINK_PREVIEW', True)), True) # Shows link preview in notification msg instead of image
ABOVE_PREVIEW = is_enabled(str(environ.get('ABOVE_PREVIEW', True)), True) # Shows link preview above the text in notification msg if True else below the msg
TMDB_API_KEY = environ.get('TMDB_API_KEY', 'http://www.omdbapi.com/?i=tt3896198&apikey=58a00e17') # preffer to use your own tmdb API Key get it from https://www.themoviedb.org/settings/api
TMDB_POSTER = is_enabled(str(environ.get('TMDB_POSTER', False)), False) # Shows TMDB poster in notification msg
LANDSCAPE_POSTER = is_enabled(str(environ.get('LANDSCAPE_POSTER', True)), True) # Shows landscape poster in notification msg

# ============================
# Verification Settings
# ============================
IS_VERIFY = is_enabled(environ.get('IS_VERIFY', 'True'), True)  # Verification On (True) / Off (False)
LOG_VR_CHANNEL = int(environ.get('LOG_VR_CHANNEL', '-100')) #Verification Channel Id 
LOG_API_CHANNEL = int(environ.get('LOG_API_CHANNEL', '-100')) #If Anyone Set Your Bot In Any Group And Set Shortner In That Group Then In This Channel The All Details Come
VERIFY_IMG = environ.get("VERIFY_IMG", "https://telegra.ph/file/9ecc5d6e4df5b83424896.jpg")

TUTORIAL = environ.get("TUTORIAL", "https://t.me/roaroicgroup")   # Tutorial link for verification
TUTORIAL_2 = environ.get("TUTORIAL_2", "https://t.me/roaroic0")   # Second tutorial link for verification
TUTORIAL_3 = environ.get("TUTORIAL_3", "https://t.me/roaroic1")   # Third tutorial link for verification

# Verification (Must Fill All Veriables. Else You Got Error
SHORTENER_API = environ.get("SHORTENER_API", "67088d44ce41560a1129a9ed28bf7793bc15fbed") # Shortener API key
SHORTENER_WEBSITE = environ.get("SHORTENER_WEBSITE", "linkpays.in") # Shortener website

SHORTENER_API2 = environ.get("SHORTENER_API2", "67088d44ce41560a1129a9ed28bf7793bc15fbed")  # Shortener API key for second website
SHORTENER_WEBSITE2 = environ.get("SHORTENER_WEBSITE2", "linkpays.in") # Shortener website for second website

SHORTENER_API3 = environ.get("SHORTENER_API3", "67088d44ce41560a1129a9ed28bf7793bc15fbed")  
SHORTENER_WEBSITE3 = environ.get("SHORTENER_WEBSITE3", "linkpays.in") # Shortener website for third website

FREE_FILES_BEFORE_VERIFY = int(environ.get('FREE_FILES_BEFORE_VERIFY', "3"))  # Free files EVERY user gets per day (resets 12 AM IST) before verification starts (0 = disabled)
SENDALL_PREMIUM_ONLY = is_enabled(environ.get('SENDALL_PREMIUM_ONLY', "True"), True)  # True = 'Send All' button only for Premium users (admins always allowed)
TWO_VERIFY_GAP = int(environ.get('TWO_VERIFY_GAP', "1200")) # Time gap for two-step verification in seconds (default: 20 minutes)
THREE_VERIFY_GAP = int(environ.get('THREE_VERIFY_GAP', "54000"))    

# ============================
# Channel & Group Links Configuration
# ============================
GRP_LNK = environ.get('GRP_LNK', 'https://t.me/roaroicgroup') # Group link for the bot
OWNER_LNK = environ.get('OWNER_LNK', 'https://t.me/roaroic0') # Owner link for the bot
UPDATE_CHNL_LNK = environ.get('UPDATE_CHNL_LNK', 'https://t.me/roaroic1') # Update channel link for the bot

# ============================
# User Configuration
# ============================
auth_users = [int(user) if id_pattern.search(user) else user for user in environ.get('AUTH_USERS', '').split()]
AUTH_USERS = (auth_users + ADMINS) if auth_users else []
PREMIUM_USER = [int(user) if id_pattern.search(user) else user for user in environ.get('PREMIUM_USER', '').split()]

# ============================
# Miscellaneous Configuration
# ============================
TRENDING_PREMIUM_ONLY = is_enabled(environ.get('TRENDING_PREMIUM_ONLY', "True"), True) # True = Trending/Top-search only for Premium users (admins always allowed)
ULTRA_FAST_MODE = is_enabled(environ.get('ULTRA_FAST_MODE', "True"), True) # Set to True for fast search, False for original search

MAX_B_TN = environ.get("MAX_B_TN", "5") # Maximum number of buttons in a row (default: 5)
PORT = int(environ.get("PORT", "8080"))  # Port for the web server (default: 8080)
MSG_ALRT = environ.get('MSG_ALRT', 'Share & Support Us ♥️') # Alert message for users
DELETE_TIME = int(environ.get("DELETE_TIME", "300"))  #  deletion time in seconds (default: 5 minutes). Adjust as per your needs.
CUSTOM_FILE_CAPTION = environ.get("CUSTOM_FILE_CAPTION", f"{script.CAPTION}")   # Custom caption for files
BATCH_FILE_CAPTION = environ.get("BATCH_FILE_CAPTION", CUSTOM_FILE_CAPTION) # Custom caption for batch files
IMDB_TEMPLATE = environ.get("IMDB_TEMPLATE", f"{script.IMDB_TEMPLATE_TXT}")     # Custom IMDB template 
MAX_LIST_ELM = environ.get("MAX_LIST_ELM", None) # Maximum number of elements in a list (default: None, no limit)
INDEX_REQ_CHANNEL = int(environ.get('INDEX_REQ_CHANNEL', LOG_CHANNEL))  # Index Request Channel ID (make sure bot is admin)
NO_RESULTS_MSG = is_enabled(str(environ.get("NO_RESULTS_MSG", True)), True)  # True if you want no results messages in Log Channel
MAX_BTN = is_enabled((environ.get('MAX_BTN', "True")), True)    # Max Button On (True) / Off (False)
P_TTI_SHOW_OFF = is_enabled((environ.get('P_TTI_SHOW_OFF', "True")), True)    # P_TTI_SHOW_OFF On (True) / Off (False)
IMDB = is_enabled((environ.get('IMDB', "False")),False)    # IMDB Results On (True) / Off (False)
TMDB_ON_SEARCH = is_enabled((environ.get('TMDB_ON_SEARCH', "False")), False)    # Use TMDB Poster On Search Results
AUTO_FFILTER = is_enabled((environ.get('AUTO_FFILTER', "True")), True) # Auto Filter On (True) / Off (False)
AUTO_DELETE = is_enabled((environ.get('AUTO_DELETE', "True")), True) # Auto Delete On (True) / Off (False)
LONG_IMDB_DESCRIPTION = is_enabled(environ.get("LONG_IMDB_DESCRIPTION", "False"), False) # Long IMDB Description On (True) / Off (False)
SPELL_CHECK_REPLY = is_enabled(environ.get("SPELL_CHECK_REPLY", "True"), True) # Spell Check Mode On (True) / Off (False)
MELCOW_NEW_USERS = is_enabled((environ.get('MELCOW_NEW_USERS', "False")), False) # Melcow New Users On (True) / Off (False)
PROTECT_CONTENT = is_enabled((environ.get('PROTECT_CONTENT', "False")), False) # Protect Content On (True) / Off (False)
PM_SEARCH = is_enabled(str(environ.get('PM_SEARCH', True)), True)  # PM Search On (True) / Off (False)
EMOJI_MODE = is_enabled(str(environ.get('EMOJI_MODE', True)), True)  # Emoji status On (True) / Off (False)
BUTTON_MODE = is_enabled((environ.get('BUTTON_MODE', "True")), True) # pm & Group button or link mode (True) / Off (False)
STREAM_MODE = is_enabled(environ.get('STREAM_MODE', "True"), True) # Set Stream mode True or False
PREMIUM_STREAM_MODE = is_enabled(environ.get('PREMIUM_STREAM_MODE', "True"), True) # Set Stream mode True or False only for premium users


# ============================
# Bot Configuration
# ============================

AUTH_REQ_CHANNELS = [int(ch) for ch in auth_req_channels.split() if ch and id_pattern.match(ch)] 
AUTH_CHANNELS = [int(ch) for ch in auth_channels.split() if ch and id_pattern.match(ch)]
REQST_CHANNEL = int(reqst_channel) if reqst_channel and id_pattern.search(reqst_channel) else None
SUPPORT_CHAT_ID = int(support_chat_id) if support_chat_id and id_pattern.search(support_chat_id) else None
LANGUAGES = {"ᴍᴀʟᴀʏᴀʟᴀᴍ":"mal","ᴛᴀᴍɪʟ":"tam","ᴇɴɢʟɪsʜ":"eng","ʜɪɴᴅɪ":"hin","ᴛᴇʟᴜɢᴜ":"tel","ᴋᴀɴɴᴀᴅᴀ":"kan","ɢᴜᴊᴀʀᴀᴛɪ":"guj","ᴍᴀʀᴀᴛʜɪ":"mar","ᴘᴜɴᴊᴀʙɪ":"pun"}
QUALITIES = ["360P", "480P", "720P", "1080P", "1440P", "2160P", "4K"]

SEASON_COUNT = 12
SEASONS = [f"S{str(i).zfill(2)}" for i in range(1, SEASON_COUNT + 1)]

BAD_WORDS = {
    "PrivateMovieZ",
    "toonworld4all",
    "themoviesboss",
    "1tamilmv",
    "tamilblasters",
    "1tamilblasters",
    "skymovieshd",
    "extraflix",
    "hdm2",
    "moviesmod",
    "hdhub4u",
    "mkvcinemas",
    "primefix",
    "join",
    "www",
    "villa",
    "tg",
    "original"
} # Set of bad words to filter out
   

# ============================
# Server & Web Configuration
# ============================

# Render sets RENDER_EXTERNAL_HOSTNAME (e.g. mybot.onrender.com) automatically
ON_RENDER = 'RENDER' in environ
NO_PORT = is_enabled(environ.get('NO_PORT', "True" if ON_RENDER else "False"), ON_RENDER)
APP_NAME = None
if 'DYNO' in environ:
    ON_HEROKU = True
    APP_NAME = environ.get('APP_NAME')
else:
    ON_HEROKU = False
BIND_ADRESS = str(getenv('WEB_SERVER_BIND_ADDRESS', '0.0.0.0'))
if getenv('FQDN'):
    FQDN = str(getenv('FQDN'))
elif ON_RENDER and getenv('RENDER_EXTERNAL_HOSTNAME'):
    FQDN = str(getenv('RENDER_EXTERNAL_HOSTNAME'))
elif ON_HEROKU:
    FQDN = APP_NAME + '.herokuapp.com'
else:
    FQDN = BIND_ADRESS
URL = "https://{}/".format(FQDN) if ON_HEROKU or NO_PORT else "https://{}/".format(FQDN, PORT)
SLEEP_THRESHOLD = int(environ.get('SLEEP_THRESHOLD', '60'))
WORKERS = int(environ.get('WORKERS', '4'))
SESSION_NAME = str(environ.get('SESSION_NAME', 'dreamXBotz'))
MULTI_CLIENT = False
name = str(environ.get('name', 'DREAMXBOTZ'))
PING_INTERVAL = int(environ.get("PING_INTERVAL", "600"))  # 10 minutes (Render free sleeps after 15 min idle)
if 'DYNO' in environ:
    ON_HEROKU = True
    APP_NAME = str(getenv('APP_NAME'))
else:
    ON_HEROKU = False
HAS_SSL = is_enabled(str(getenv('HAS_SSL', True)), True)
if HAS_SSL:
    URL = "https://{}/".format(FQDN)
else:
    URL = "http://{}/".format(FQDN)

# ============================
# Reactions Configuration
# ============================
REACTIONS = ["🤝", "😇", "🤗", "😍", "👍", "🎅", "😐", "🥰", "🤩", "😱", "🤣", "😘", "👏", "😛", "😈", "🎉", "⚡️", "🫡", "🤓", "😎", "🏆", "🔥", "🤭", "🌚", "🆒", "👻", "😁", "🤯", "🙏", "👌", "🕊", "🤡", "🥴", "🐳", "💯", "🍓", "🍾", "💋", "😭", "👀", "🎃", "🙈", "🎄", "💅", "🗿", "🦄", "👾"]

# ============================
# Commands Bot
# ============================
Bot_cmds = {
     "start": "Sᴛᴀʀᴛ Mᴇ Bᴀʙʏ",
    "stats": "Gᴇᴛ Bᴏᴛ Sᴛᴀᴛs",
    "alive": " Cʜᴇᴄᴋ Bᴏᴛ Aʟɪᴠᴇ ᴏʀ Nᴏᴛ ",
    "settings": "ᴄʜᴀɴɢᴇ sᴇᴛᴛɪɴɢs",
    "id": "ɢᴇᴛ ɪᴅ ᴛᴇʟᴇɢʀᴀᴍ ",
    "info": "Gᴇᴛ Usᴇʀ ɪɴғᴏ ",
    "del_msg": "ʀᴇᴍᴏᴠᴇ ғɪʟᴇ ɴᴀᴍᴇ ᴄᴏʟʟᴇᴄᴛɪᴏɴ ɴᴏтɪғɪᴄᴀᴛɪᴏɴ...",
    "movie_update": "ᴏɴ ᴏғғ ᴀᴄᴄᴏʀᴅɪɴɢ ʏᴏᴜʀ ɴᴇᴇᴅᴇᴅ...",
    "pm_search": "ᴘᴍ sᴇᴀʀᴄʜ ᴏɴ ᴏғғ ᴀᴄᴄᴏʀᴅɪɴɢ ʏᴏᴜʀ ɴᴇᴇᴅᴇᴅ...",
    "trendlist": "Gᴇᴛ Tᴏᴘ Tʀᴀɴᴅɪɴɢ Sᴇᴀʀᴄʜ Lɪsᴛ",
    "broadcast": "ʙʀᴏᴀᴅᴄᴀꜱᴛ ᴀ ᴍᴇꜱꜱᴀɢᴇ ᴛᴏ ᴀʟʟ ᴜꜱᴇʀꜱ.",
    "grp_broadcast": "ʙʀᴏᴀᴅᴄᴀsᴛ ᴀ ᴍᴇssᴀɢᴇ ᴛᴏ ᴀʟʟ ᴄᴏɴɴᴇᴄᴛᴇᴅ ɢʀᴏᴜᴘs",
    "send": "ꜱᴇɴᴅ ᴍᴇꜱꜱᴀɢᴇ ᴛᴏ ᴀ ᴘᴀʀᴛɪᴄᴜʟᴀʀ ᴜꜱᴇʀ.",
    "add_premium": "ᴀᴅᴅ ᴀɴʏ ᴜꜱᴇʀ ᴛᴏ ᴘʀᴇᴍɪᴜᴍ.",
    "remove_premium": "ʀᴇᴍᴏᴠᴇ ᴀɴʏ ᴜꜱᴇʀ ꜰʀᴏᴍ ᴘʀᴇᴍɪᴜᴍ.",
    "premium_users": "ɢᴇᴛ ʟɪꜱᴛ ᴏꜰ ᴘʀᴇᴍɪᴜᴍ ᴜꜱᴇʀꜱ.",
    "restart": "ʀᴇꜱᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ.",
    "group_cmd": "ɢʀᴏᴜᴘ ᴄᴏᴍᴍᴀɴᴅ ʟɪsᴛ",
    "admin_cmd": "ᴀᴅᴍɪɴ ᴄᴏᴍᴍᴀɴᴅs ʟɪsᴛ.",
    "reset_group": "Group Setting Default",
    "trial_reset": "User Trial Reset"
}


#Don't Change Anything Here
if MULTIPLE_DB == False:
    DATABASE_URI = DATABASE_URI
    DATABASE_URI2 = DATABASE_URI
else:
    DATABASE_URI = DATABASE_URI
    DATABASE_URI2 = DATABASE_URI2

# ============================
# Logs Configuration
# ============================
LOG_STR = "Current Customized Configurations are:-\n"
LOG_STR += ("IMDB Results are enabled, Bot will be showing imdb details for your queries.\n" if IMDB else "IMDB Results are disabled.\n")
LOG_STR += ("P_TTI_SHOW_OFF found, Users will be redirected to send /start to Bot PM instead of sending file directly.\n" if P_TTI_SHOW_OFF else "P_TTI_SHOW_OFF is disabled, files will be sent in PM instead of starting the bot.\n")
LOG_STR += ("BUTTON_MODE is found, filename and file size will be shown in a single button instead of two separate buttons.\n" if BUTTON_MODE else "BUTTON_MODE is disabled, filename and file size will be shown as different buttons.\n")
LOG_STR += (f"CUSTOM_FILE_CAPTION enabled with value {CUSTOM_FILE_CAPTION}, your files will be sent along with this customized caption.\n" if CUSTOM_FILE_CAPTION else "No CUSTOM_FILE_CAPTION Found, Default captions of file will be used.\n")
LOG_STR += ("Long IMDB storyline enabled." if LONG_IMDB_DESCRIPTION else "LONG_IMDB_DESCRIPTION is disabled, Plot will be shorter.\n")
LOG_STR += ("Spell Check Mode is enabled, bot will be suggesting related movies if movie name is misspelled.\n" if SPELL_CHECK_REPLY else "Spell Check Mode is disabled.\n")
