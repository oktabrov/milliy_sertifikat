# Deploying to alwaysdata

The whole thing is one ASGI process: the Telegram webhook, the Mini App API and
the Mini App static files all come off the same port and the same certificate.
That fits alwaysdata's "user program" site type exactly, and it means there is
no separate worker to keep alive.

Your account already gives you `https://<account>.alwaysdata.net`, which
satisfies Telegram's HTTPS requirement for both the webhook and the Mini App.

---

## 1. Storage: nothing to set up

There is no database. Users, tests and attempts live in three JSON files under
`DATA_DIR` (default `./data`), written atomically and guarded by a lock so
simultaneous submissions cannot overwrite one another.

One consequence to respect: **run a single worker.** Two uvicorn processes would
each hold their own copy in memory and clobber each other's writes. The command
below starts one.

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
~/www/testbot/venv/bin/pip install --no-cache-dir -r requirements.txt
```

Measured footprint, which matters against the free plan's quota:

| | Size |
|---|---|
| virtualenv as installed | 46 MB |
| after `scripts/deploy.sh` strips pip and bytecode caches | **19 MB** |
| application code | 0.4 MB |

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
DATA_DIR=./data
ADMIN_IDS=<your Telegram user id>
REQUIRED_CHANNELS=@your_channel
```

`chmod 600 .env` — it holds the bot token.

## 5. Create the site

**Web → Sites → Add a site**

- **Type:** User program
- **Command:**

  ```
  /home/<account>/www/testbot/venv/bin/python -B -m uvicorn app.main:app --host $IP --port $PORT
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
bash ~/www/testbot/scripts/deploy.sh
```

Then restart the site from the panel. The script pulls, reinstalls, reclaims
space and re-validates the configuration.

Back up your data by copying the three files:

```bash
tar czf ~/testbot-backup-$(date +%F).tar.gz -C ~/www/testbot data
```

---

## Troubleshooting

**The site will not start.** Read the log under **Web → Sites → Logs**. A
missing `BOT_TOKEN` raises at import: settings are validated eagerly on purpose,
so the process fails loudly instead of running half-configured.

**The bot does not answer.** Check `getWebhookInfo` for `last_error_message`. If
it shows a TLS or 404 error, `WEBHOOK_BASE` or `WEBHOOK_SECRET` does not match
what the site is actually serving.

**The Mini App button does nothing, or opens an old address.** Reply keyboards
persist in a chat until they are replaced, and the Mini App URL is baked into
the button at the moment it is sent. After changing `WEBHOOK_BASE`, every user
still holds a button pointing at the previous address. Send `/ms` (or `/start`)
to rebuild it. Telegram also silently drops `web_app` buttons whose URL is not
HTTPS, so check `WEBHOOK_BASE` starts with `https://`.

**Checking the deployment without SSH.** `/healthz` reports whether the bot can
actually receive updates, not just whether the web server is up:

```bash
curl https://<account>.alwaysdata.net/healthz
```

```json
{"status":"ok","mode":"webhook","bot_ready":true,
 "miniapp_base":"https://<account>.alwaysdata.net/app"}
```

`"status":"degraded"` with HTTP 503 means the site is serving but the bot is
deaf; `webhook_error` says why. Check `miniapp_base` matches your real domain —
if it does not, that is the value going into every Mini App button.

**Disk quota on the free plan.** The 100 MB limit is why nothing here depends on
numpy, scipy, an ORM or a database driver. If you add packages, check
`du -sh ~/www/testbot/venv` before committing to them.

**Cold restarts lose FSM state.** Registration state lives in memory, so a
student mid-`/start` has to send `/start` again after a restart. Everything
persistent — users, tests, attempts, results — is in the JSON files.
