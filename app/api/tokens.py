"""HMAC-signed tokens for Mini App authentication.

When Telegram fails to deliver initData (which happens on some clients/platforms),
the bot generates a signed token containing the user_id and embeds it in the
Mini App URL. The server accepts either initData OR a valid token.

Tokens are signed with the bot token using HMAC-SHA256, same trust root as
Telegram's own initData verification.
"""

from __future__ import annotations

import hashlib
import hmac
import time

TOKEN_MAX_AGE = 3600  # 1 hour, same as initData


def create_token(user_id: int, bot_token: str, now: float | None = None) -> str:
    """Create a signed token: ``user_id:timestamp:signature``."""
    ts = int(now if now is not None else time.time())
    payload = f"{user_id}:{ts}"
    sig = hmac.new(
        bot_token.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()[:32]
    return f"{payload}:{sig}"


def verify_token(
    token: str,
    bot_token: str,
    max_age: int = TOKEN_MAX_AGE,
    now: float | None = None,
) -> int:
    """Return the user_id if the token is valid, or raise ValueError."""
    if not token:
        raise ValueError("empty token")

    parts = token.split(":")
    if len(parts) != 3:
        raise ValueError("bad token format")

    try:
        user_id = int(parts[0])
        ts = int(parts[1])
    except (ValueError, IndexError) as e:
        raise ValueError("bad token fields") from e

    sig = parts[2]
    payload = f"{user_id}:{ts}"
    expected = hmac.new(
        bot_token.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()[:32]

    if not hmac.compare_digest(expected, sig):
        raise ValueError("bad token signature")

    current = time.time() if now is None else now
    if current - ts > max_age:
        raise ValueError("token expired")

    return user_id
