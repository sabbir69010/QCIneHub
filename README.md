# Q Cine Hub Bot

Telegram bot that serves movies by unique code. Python 3.11+, aiogram 3, SQLite.

## 1. Architecture

```
Telegram ─► Dispatcher ─► Throttling (outer) ─► admin router (AdminOnly middleware, FSM)
                                              └► user router
                                   │
                      MovieService (SQL)   StorageService (storage channel)
                                   │
                              SQLite (WAL)
```

| Folder | Responsibility |
|---|---|
| `bot.py` | Wiring: settings, DB, services, middleware, polling, graceful shutdown |
| `config.py` | Env-var settings (token never printed) |
| `database.py` | Connection, PRAGMAs, schema |
| `models/` | `Movie` dataclass |
| `services/` | `MovieService` (CRUD), `StorageService` (Telegram storage), notifications, exceptions |
| `handlers/` | `user.py`, `admin.py` (FSM flows), `errors.py`, `states.py` |
| `keyboards/` | Inline keyboards + typed callback data |
| `middleware/` | `AdminOnlyMiddleware`, `ThrottlingMiddleware` |
| `utils/` | Validators, logging setup |

## 2. Data flow

**User:** `/start` → send code → normalise (`strip().upper()`) + format check → indexed lookup → buttons.
- *Download*: `copy_message(from_chat=STORAGE, message_id=file_message_id)`. If Telegram reports the message gone, the user gets a notice and admins are alerted.
- *Watch Online*: bot sends only a message with a `🎥 Watch Online` URL button. Missing link → alert; broken link → admins notified.

**Admin `/addmovie`:** code → name → description → link → file. If the file is forwarded *from the storage channel*, its message ID is reused. Otherwise the bot posts it into the storage channel by `file_id` and stores the new message ID. If the DB insert fails, the copy it just made is deleted.

The bot never deletes files you placed in the storage channel yourself.

## 3. Database schema

```sql
CREATE TABLE movies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    movie_code TEXT NOT NULL UNIQUE CHECK (length(movie_code) BETWEEN 3 AND 20),
    movie_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    file_message_id INTEGER,
    online_link TEXT,
    added_date TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    file_id TEXT, file_unique_id TEXT, file_name TEXT, file_size INTEGER
);
```
`UNIQUE` gives an index (fast lookup) and duplicate protection at DB level. The last four columns are the "file information" extras.

## 4. Setup

1. Create a bot with **@BotFather**, copy the token.
2. Create a **private channel** for storage and add the bot as **admin** (permission to post messages).
3. Channel ID: open the channel in Telegram Web; the URL number prefixed with `-100` is the ID (e.g. `-1001234567890`).
4. Your user ID: message **@userinfobot**.
5. Local run:
```bash
cp .env.example .env      # fill in the values
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python bot.py
```
6. In Telegram: `/admin`, then `/addmovie`.

## 5. Railway deployment

(Railway's UI changes occasionally. Check their docs if a label differs.)

1. Push the project to a **private** GitHub repo (`.env` is git-ignored).
2. Railway → **New Project → Deploy from GitHub repo**.
3. Service → **Variables**: `BOT_TOKEN`, `ADMIN_IDS`, `STORAGE_CHAT_ID`, `DB_PATH=/data/qcine.db`.
4. Service → add a **Volume** mounted at `/data` so SQLite survives redeploys. Without it the DB is wiped on every deploy.
5. Start command is `python bot.py` (set by `railway.json`; a `Dockerfile` is also included).
6. No public domain needed (long polling). Keep **one** replica: two pollers conflict.
7. Check **Deploy Logs** for `Starting @yourbot` and `Storage chat OK`.

## 6. VPS deployment (Ubuntu 22.04/24.04)

```bash
sudo apt update && sudo apt install -y python3 python3-venv git sqlite3 ufw
# Ubuntu 22.04 ships Python 3.10: install 3.11+ (deadsnakes PPA) or use uv.
sudo useradd -r -m -d /opt/qcine_bot -s /usr/sbin/nologin qcine
sudo -u qcine git clone <your-private-repo> /opt/qcine_bot
cd /opt/qcine_bot
sudo -u qcine python3 -m venv .venv
sudo -u qcine .venv/bin/pip install -r requirements.txt
sudo -u qcine cp .env.example .env && sudo -u qcine nano .env
sudo chmod 600 .env
sudo cp deploy/qcine-bot.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now qcine-bot
journalctl -u qcine-bot -f
```
Firewall (no inbound ports needed except SSH): `sudo ufw allow OpenSSH && sudo ufw enable`.
Backups: `sudo crontab -e` → `15 3 * * * /opt/qcine_bot/deploy/backup.sh`.
Update: `git pull && .venv/bin/pip install -r requirements.txt && sudo systemctl restart qcine-bot`.

## 7. Security best practices

- Token only in env vars; if it leaks, revoke it via @BotFather `/revoke`.
- Admin allow-list by numeric user ID, enforced by middleware. Admin commands only work in private chats.
- Storage channel stays private; only the bot and trusted admins are members.
- `.env` mode 600, DB file mode 600, bot runs as an unprivileged user (systemd hardening included).
- Parameterised SQL only; the single dynamic `SET` clause uses a column whitelist.
- All user text is HTML-escaped; URLs must be http(s).
- Throttling per user; logs rotate (5 MB x 5) and contain no secrets.
- Backups off-box (copy `backups/` to object storage). Keep the bot's dependencies updated.
- Consider `protect_content=True` in `copy_message` if you want to block forwarding of downloaded files.

## 8. Operating notes and limits

- Telegram bots can send files up to **2 GB**. Larger movies need splitting.
- Telegram caps bulk sending (about 30 messages/second overall), which is your real scaling limit, not SQLite.
- FSM state is in memory: an admin flow in progress is lost on restart (just re-run the command).
- Edits cannot change a movie code (delete and re-add instead).

## 9. Future improvements and scalability

- **Webhook mode** behind Nginx/Caddy for lower latency; **PostgreSQL** + **Redis** (FSM storage, throttling) for multiple instances.
- Download/lookup analytics table; popular-movie stats for admins.
- Forced-subscription check (user must join your channel first).
- Expiring signed streaming links; per-user daily download quotas.
- Fuzzy/name search with SQLite FTS5; bulk CSV import; multiple files or qualities per movie.
- Admin roles (owner/editor), audit log, schema migrations (Alembic), unit tests with `pytest-asyncio`, Sentry error tracking, Docker Compose, i18n.
