"""Telegram Mini App authentication.

Two auth methods are supported:
1. initData (Telegram's HMAC-signed session string) — the standard method
2. Bot-signed token (user_id:timestamp:hmac) — fallback when initData is
   unavailable due to Telegram client issues

The server tries initData first; if that fails, it tries the token.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException, Query, status

from app.api.tokens import verify_token
from app.config import get_settings

# Telegram refreshes initData when the app reopens; an hour is generous.
MAX_AUTH_AGE_SECONDS = 3600


@dataclass(frozen=True)
class WebAppUser:
    id: int
    first_name: str = ""
    last_name: str = ""
    username: str | None = None

    @property
    def full_name(self) -> str:
        return " ".join(part for part in (self.first_name, self.last_name) if part).strip()


class InitDataError(ValueError):
    pass


def verify_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = MAX_AUTH_AGE_SECONDS,
    now: float | None = None,
) -> WebAppUser:
    """Return the authenticated user, or raise `InitDataError`."""
    if not init_data:
        raise InitDataError("empty initData")

    fields = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = fields.pop("hash", "")
    if not received_hash:
        raise InitDataError("missing hash")

    check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise InitDataError("bad signature")

    try:
        auth_date = int(fields.get("auth_date", "0"))
    except ValueError as error:
        raise InitDataError("bad auth_date") from error

    current = time.time() if now is None else now
    if max_age_seconds and current - auth_date > max_age_seconds:
        raise InitDataError("initData expired")

    try:
        payload = json.loads(fields.get("user", "{}"))
    except json.JSONDecodeError as error:
        raise InitDataError("bad user payload") from error

    if not isinstance(payload, dict) or "id" not in payload:
        raise InitDataError("no user in initData")

    return WebAppUser(
        id=int(payload["id"]),
        first_name=payload.get("first_name", "") or "",
        last_name=payload.get("last_name", "") or "",
        username=payload.get("username"),
    )


async def require_web_app_user(
    authorization: str | None = Header(default=None),
    x_init_data: str | None = Header(default=None, alias="X-Init-Data"),
    x_app_token: str | None = Header(default=None, alias="X-App-Token"),
) -> WebAppUser:
    """FastAPI dependency. Tries initData first, falls back to bot-signed token."""
    settings = get_settings()

    # 1. Try initData (standard Telegram auth)
    raw = ""
    if authorization and authorization.lower().startswith("tma "):
        raw = authorization[4:].strip()
    elif x_init_data:
        raw = x_init_data.strip()

    if raw:
        try:
            return verify_init_data(raw, settings.bot_token)
        except InitDataError:
            pass  # Fall through to token auth

    # 2. Try bot-signed token (fallback)
    token = x_app_token.strip() if x_app_token else ""
    if not token and authorization and authorization.lower().startswith("token "):
        token = authorization[6:].strip()

    if token:
        try:
            user_id = verify_token(token, settings.bot_token)
            return WebAppUser(id=user_id)
        except ValueError:
            pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Avtorizatsiya xatosi. Mini ilovani bot orqali oching.",
    )
