# 👑 Admin Panel + 📨 Contact-Admin

Added in `plugins/admin_panel.py` (auto-loaded, no new env vars, no new dependencies).

## Admin
| Command | What it does |
|---|---|
| `/panel` or `/admin` | Colourful control panel: Dashboard, Users, Premium, Broadcast, Bans, Settings, Inbox, System, Commands |
| `/userinfo <id>` (or reply) | User card with ✍️ Message, 🚫 Ban/✅ Unban, 💎 +7d/+30d/+1y, ➖ Remove premium |
| `/tickets` | Open support tickets |
| `/maintenance on\|off` | Users get a maintenance notice (they can still /contact) |
| `/cancel` | Cancel a pending reply / broadcast compose |

Settings page toggles: PM search, movie-update notifications, maintenance mode, contact-admin inbox.
Broadcast page: ✍️ Compose → send any message → ✅ confirm → live progress bar with ⏹ Stop.

## Users
`/contact` (or the **📨 Contact Admin** button on /start) → write anything → admins receive it
with `[Reply] [Info] [Close] [Ban]`. Admin replies either by **swipe-replying** to the message or by
tapping **Reply** and sending the next message. Users get an **✍️ Reply to Admin** button on every answer.
Anti-spam: 6 messages/minute, contact mode auto-ends after 10 min idle.

Tickets + message→user routing are stored in MongoDB (collections `tickets`, `ticket_map`, `counters`;
routing entries expire after 30 days), so replies survive restarts.

Existing `/chat`, `/endchat`, `/msg` (plugins/admin_chat.py) keep working unchanged.
