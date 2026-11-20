## 🔔 New Version Released – V1.4

- ✅ Spell Check Toggle (Group Only)
- ✅ Group Owners Can Manage Settings via Bot PM
- ✅ Reset All Group Settings (Owner Only)
- ✅ 3 Verification System

---

## 🌟 Features
- ✅ Double db support 
- ✅ Stream Mode Toggle  
- ✅ 3 User Verification  
- ✅ Multi FSub Admin & Group Support  
- ✅ Auto Movie Info Updates  
- ✅ PM Search Toggle  
- ✅ Verified User Counter  
- ✅ Trending Titles  
- ✅ Advanced AI Spelling Correction  
- ✅ Request to Join via FSub (Admins Only)  
- ✅ Verified User Database Save  
- ✅ Superfast User Broadcast  
- ✅ Refer & Earn Premium  
- ✅ Top Searching  
- ✅ Best Streaming Website Integration  
- ✅ Premium Membership Management  
- ✅ Online Streaming & Fast Download  
- ✅ File Indexing Above 2GB  
- ✅ PreDVD & CamRip Auto Deletion  
- ✅ Multiple File Deletion  
- ✅ Settings Menu  
- ✅ Welcome Message  
- ✅ Auto File Filtering    
- ✅ Single Filter Button  
- ✅ Bot PM File Send Mode  
- ✅ Auto File Send  
- ✅ Forward Restriction  
- ✅ File Protection  
- ✅ Admin Commands  
- ✅ Group Broadcast  
- ✅ Full File Indexing Support  
- ✅ ID & User Info  
- ✅ Stats & Analytics  
- ✅ User Ban/Unban  
- ✅ Chat Leave/Disable  
- ✅ Auto Delete Old Files  
- ✅ …and more!

---

## ⚙️ Commands

```bash
movie_update        – Toggle movie update notifications
pm_search           – Toggle private message search
verification        – View total verified users
top                 – Search top trending items
start               – Start the bot
settings            – Modify bot settings
plan                – View available premium plans
myplan              – Check your active plan
stats               – View database stats
info                – Get user info
id                  – Get Telegram ID
link                – Create single post link
batch               – Create bulk post link
deleteall           – Delete all files from DB
delete              – Delete a specific file
deletefiles         – Remove PreDVD and CamRip files
broadcast           – Broadcast to users
grp_broadcast       – Broadcast to groups
enable              – Enable group joining
disable             – Disable group
leave               – Leave group
ban                 – Ban user from bot
unban               – Unban user
add_premium         – Add premium access
remove_premium      – Remove premium access
premium_users       – List premium users
restart             – Restart the bot
```

---

<p align="center"><b>Jai Shree Krishna 🙏😉</b></p>


## TMDB + OMDb (movie details / posters)

Set both keys in your env (Render → Environment):

| Var | Where to get it | What it gives |
|-----|-----------------|---------------|
| `TMDB_API_KEY` | themoviedb.org/settings/api | poster, landscape backdrop, cast, crew |
| `OMDB_API_KEY` | omdbapi.com/apikey.aspx (free, 1000/day) | IMDb rating + votes, Rotten Tomatoes, Metascore, awards |

Order: **TMDB → merged with OMDb → fallback IMDb scraping**. If TMDB fails, OMDb alone is used; if OMDb quota ends, TMDB keeps working. OMDb results are cached for 24h.
Extra template placeholders you can use: `{rt_rating}` `{metascore}` `{awards}`.
