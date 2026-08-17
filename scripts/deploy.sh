#!/usr/bin/env bash
#
# Run this ON the alwaysdata server, over SSH:
#
#   ssh <account>@ssh-<account>.alwaysdata.net
#   bash <(curl -sL https://raw.githubusercontent.com/tohir-dev/telegram_bot/main/scripts/deploy.sh)
#
# Or, once the repo is cloned:  bash ~/www/testbot/scripts/deploy.sh
#
# Idempotent: safe to re-run to update an existing deployment.

set -euo pipefail

REPO="${REPO:-https://github.com/tohir-dev/telegram_bot.git}"
APP_DIR="${APP_DIR:-$HOME/www/testbot}"
PYTHON="${PYTHON:-python3.11}"

info() { printf '\033[1;34m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$1"; }

# --- Python -----------------------------------------------------------------

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  warn "$PYTHON not found. Available:"
  ls /usr/bin/python3* 2>/dev/null || true
  warn "Re-run with:  PYTHON=python3.12 bash $0"
  exit 1
fi
info "Using $($PYTHON --version)"

# --- Code -------------------------------------------------------------------

if [ -d "$APP_DIR/.git" ]; then
  info "Updating $APP_DIR"
  git -C "$APP_DIR" pull --ff-only
else
  info "Cloning into $APP_DIR"
  mkdir -p "$(dirname "$APP_DIR")"
  git clone "$REPO" "$APP_DIR"
fi

cd "$APP_DIR"

# --- Virtualenv -------------------------------------------------------------

if [ ! -x "$APP_DIR/venv/bin/python" ]; then
  info "Creating virtualenv"
  "$PYTHON" -m venv "$APP_DIR/venv"
fi

info "Installing dependencies"
# --no-cache-dir matters: pip's wheel cache in ~/.cache counts against the quota.
"$APP_DIR/venv/bin/pip" install --quiet --no-cache-dir -r requirements.txt

# Only pull the PostgreSQL driver when the config actually asks for it; it is
# 2.7 MB that a SQLite deployment has no use for.
if grep -qE '^DATABASE_URL=.*postgresql' "$APP_DIR/.env" 2>/dev/null; then
  info "PostgreSQL detected in .env; installing asyncpg"
  "$APP_DIR/venv/bin/pip" install --quiet --no-cache-dir asyncpg
fi

info "Reclaiming space"
# Bytecode caches roughly double the virtualenv. PYTHONDONTWRITEBYTECODE in the
# site command stops them coming back; imports are marginally slower, which
# matters far less than the quota.
find "$APP_DIR/venv" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
rm -rf "$HOME/.cache/pip" 2>/dev/null || true

USED=$(du -sh "$APP_DIR/venv" | cut -f1)
info "Virtualenv now uses $USED (free plan allows 100M for the whole account)"
info "Total account usage: $(du -sh "$HOME" 2>/dev/null | cut -f1)"

# --- Configuration ----------------------------------------------------------

if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
  warn ".env created from the template — it is NOT configured yet."
  warn "Edit it now:  nano $APP_DIR/.env"
  warn ""
  warn "You must set at minimum:"
  warn "  BOT_TOKEN       from @BotFather"
  warn "  WEBHOOK_BASE    https://<account>.alwaysdata.net"
  warn "  WEBHOOK_SECRET  a long random string, e.g. $(head -c 18 /dev/urandom | base64 | tr -d '/+=')"
  warn "  DATABASE_URL    postgresql+asyncpg://<user>:<pass>@postgresql-<account>.alwaysdata.net/<db>"
  warn "  USE_POLLING     false"
  echo
  info "Then re-run this script to verify the configuration."
  exit 0
fi

chmod 600 "$APP_DIR/.env"

# --- Verify -----------------------------------------------------------------

info "Checking configuration"
"$APP_DIR/venv/bin/python" - <<'PY'
import sys
sys.path.insert(0, ".")
try:
    from app.config import get_settings
except Exception as error:  # noqa: BLE001
    print(f"  FAIL  settings did not load: {error}")
    raise SystemExit(1)

settings = get_settings()
problems = []

if not settings.bot_token or settings.bot_token.startswith("123456:"):
    problems.append("BOT_TOKEN is not set")
if settings.use_polling:
    problems.append("USE_POLLING should be false in production (webhook mode)")
if not settings.webhook_base.startswith("https://"):
    problems.append("WEBHOOK_BASE must be an https:// URL")
if settings.webhook_secret in ("", "change-me", "change-me-to-something-random"):
    problems.append("WEBHOOK_SECRET is still the placeholder")
if settings.database_url.startswith("sqlite"):
    print("  WARN  DATABASE_URL is SQLite; PostgreSQL is recommended in production")

for problem in problems:
    print(f"  FAIL  {problem}")
if problems:
    raise SystemExit(1)

print(f"  OK    webhook  -> {settings.webhook_url}")
print(f"  OK    mini app -> {settings.miniapp_base}/answer")
print(f"  OK    database -> {settings.database_url.split('@')[-1]}")
PY

info "Checking the database connection and creating any missing tables"
"$APP_DIR/venv/bin/python" - <<'PY'
import asyncio, sys
sys.path.insert(0, ".")
from app.db.base import engine, init_models

async def main():
    await init_models()
    await engine.dispose()
    print("  OK    schema is up to date")

asyncio.run(main())
PY

echo
info "Server-side setup is complete."
echo
cat <<EOF
Remaining steps, in the alwaysdata admin panel:

  Web -> Sites -> Add a site
    Type              User program
    Command           $APP_DIR/venv/bin/python -B -m uvicorn app.main:app --host \$IP --port \$PORT
    Working directory $APP_DIR
    Addresses         <account>.alwaysdata.net

  Then restart the site and check:
    curl https://<account>.alwaysdata.net/healthz

The app registers its own Telegram webhook on startup, so there is nothing
else to call by hand.
EOF
