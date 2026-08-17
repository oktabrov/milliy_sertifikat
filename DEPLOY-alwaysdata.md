# Deploying to alwaysdata

The whole thing is one ASGI process: the Telegram webhook, the Mini App API and
the Mini App static files all come off the same port and the same certificate.
That fits alwaysdata's "user program" site type exactly, and it means there is
no separate worker to keep alive.

Your account already gives you `https://<account>.alwaysdata.net`, which
satisfies Telegram's HTTPS requirement for both the webhook and the Mini App.

---

## 1. Create the database

In the admin panel: **Databases → PostgreSQL → Add a database**.

Note the name, user and password. The host is `postgresql-<account>.alwaysdata.net`.

SQLite also works and needs no setup, but PostgreSQL is the better choice as
soon as more than a handful of students submit at once.

---

## 2. Upload the code

```bash
ssh <account>@ssh-<account>.alwaysdata.net
mkdir -p ~/www && cd ~/www
git clone https://github.com/tohir-dev/telegram_bot.git testbot
cd testbot
```

## 3. Virtualenv

alwaysdata ships several Python versions; pick 3.11 or newer.

```bash
python3.11 -m venv ~/www/testbot/venv
~/www/testbot/venv/bin/pip install --upgrade pip
~/www/testbot/venv/bin/pip install -r requirements.txt
~/www/testbot/venv/bin/pip install asyncpg      # for PostgreSQL
```

## 4. Environment file

```bash
cp .env.example .env
nano .env
```

Fill in:

```ini
BOT_TOKEN=<from @BotFather>
WEBHOOK_BASE=https://<account>.alwaysdata.net
WEBHOOK_SECRET=<a long random string>
USE_POLLING=false
DATABASE_URL=postgresql+asyncpg://<user>:<password>@postgresql-<account>.alwaysdata.net/<database>
ADMIN_IDS=<your Telegram user id>
REQUIRED_CHANNELS=@your_channel
```

`chmod 600 .env` — it holds the bot token.

## 5. Create the site

**Web → Sites → Add a site**

- **Type:** User program
- **Command:**

  ```
  /home/<account>/www/testbot/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $PORT
  ```

- **Working directory:** `/home/<account>/www/testbot`
- **Addresses:** `<account>.alwaysdata.net`

alwaysdata substitutes `$PORT` and restarts the program if it exits.

> The site type must be **User program**, not "Python WSGI". FastAPI is ASGI,
> and the WSGI runner cannot serve it.

## 6. Start it

Restart the site from the panel, then check:

```bash
curl https://<account>.alwaysdata.net/healthz
# {"status":"ok"}
```

The app registers its own webhook at startup, so there is nothing to call by
hand. Confirm with:

```bash
curl "https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo"
```

`url` should be `https://<account>.alwaysdata.net/webhook/<WEBHOOK_SECRET>` and
`pending_update_count` should be 0.

## 7. Point BotFather at the Mini App

In [@BotFather](https://t.me/BotFather):

- `/setmenubutton` → your bot → `https://<account>.alwaysdata.net/app/answer`
- `/setcommands` is handled automatically by the app on startup.

If you use `REQUIRED_CHANNELS`, add the bot as an **administrator** in each
channel — otherwise it cannot read membership, and the gate fails open by
design rather than locking everyone out.

---

## Updating

```bash
cd ~/www/testbot && git pull
~/www/testbot/venv/bin/pip install -r requirements.txt
```

Then restart the site from the panel.

New tables are created automatically at startup. Changing an existing column
needs a migration — add Alembic when that first happens.

---

## Troubleshooting

**The site will not start.** Read the log under **Web → Sites → Logs**. A
missing `BOT_TOKEN` raises at import: settings are validated eagerly on purpose,
so the process fails loudly instead of running half-configured.

**The bot does not answer.** Check `getWebhookInfo` for `last_error_message`. If
it shows a TLS or 404 error, `WEBHOOK_BASE` or `WEBHOOK_SECRET` does not match
what the site is actually serving.

**The Mini App button does nothing.** Telegram silently drops `web_app` buttons
whose URL is not HTTPS. Confirm `WEBHOOK_BASE` starts with `https://` and send
`/ms` again to rebuild the keyboard.

**Disk quota on the free plan.** The 100 MB limit is why nothing here depends on
numpy or scipy. If you add packages, `du -sh ~/www/testbot/venv` before you
commit to them.

**Cold restarts lose FSM state.** Registration state lives in memory, so a
student mid-`/start` has to send `/start` again after a restart. Everything
persistent — users, tests, attempts, results — is in the database.
