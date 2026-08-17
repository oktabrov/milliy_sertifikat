"""Channel-membership enforcement for the Mini App API.

The Mini App is a web page. Tapping its button opens it directly in Telegram's
browser and every subsequent call goes to `/api/*` — the bot's dispatcher, and
therefore its channel-gate middleware, never sees any of it.

So a gate enforced only in bot handlers is not a gate at all: a user who is not
subscribed can open the Mini App from the menu button and answer a test. The
same check has to live here, on the requests that actually carry the answers.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, Request, status

from app.services import channels as channel_service
from app.store.json_store import get_store

logger = logging.getLogger(__name__)

NOT_SUBSCRIBED = (
    "Botdan foydalanish uchun avval majburiy kanal(lar)ga a'zo bo'ling: {channels}"
)


async def require_membership(request: Request, user_id: int) -> None:
    """Raise 403 unless the user has joined every required channel.

    Does nothing when no channels are configured.
    """
    store = get_store()
    if not channel_service.current(store):
        return

    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        # No bot instance means no way to verify. Refuse rather than admit
        # everyone — the same fail-closed choice the bot-side check makes.
        logger.error("Cannot verify channel membership: no bot on app.state")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Obunani tekshirib bo'lmadi. Keyinroq urining."
        )

    missing = await channel_service.missing_for(bot, store, user_id)
    if missing:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            NOT_SUBSCRIBED.format(channels=", ".join(missing)),
        )
