"""The single ASGI app: bot webhook, Mini App API, and Mini App static files.

alwaysdata runs one command bound to $PORT, so everything lives in one process.
In production Telegram pushes updates to `/webhook/<secret>`; locally, set
USE_POLLING=true and the same app long-polls instead, so you can work without a
public HTTPS tunnel.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from aiogram.types import Update
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import routes_create, routes_test
from app.bot import create_bot, create_dispatcher, set_bot_commands
from app.config import get_settings
from app.db.base import engine, init_models

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    await init_models()

    bot = create_bot()
    dispatcher = create_dispatcher()
    app.state.bot = bot
    app.state.dispatcher = dispatcher

    polling_task: asyncio.Task | None = None

    try:
        await set_bot_commands(bot)
    except Exception:
        logger.exception("Could not publish the command list")

    if settings.use_polling:
        # Drop any webhook left over from a previous deployment, or Telegram
        # refuses to deliver updates over long polling.
        with contextlib.suppress(Exception):
            await bot.delete_webhook(drop_pending_updates=True)
        polling_task = asyncio.create_task(dispatcher.start_polling(bot))
        logger.info("Bot started in long-polling mode")
    elif settings.webhook_url:
        try:
            await bot.set_webhook(
                settings.webhook_url,
                drop_pending_updates=True,
                allowed_updates=dispatcher.resolve_used_update_types(),
            )
            logger.info("Webhook registered at %s", settings.webhook_url)
        except Exception:
            logger.exception("Could not register the webhook")
    else:
        logger.warning("Neither USE_POLLING nor WEBHOOK_BASE is set; the bot will not receive updates")

    try:
        yield
    finally:
        if polling_task is not None:
            polling_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await polling_task
        with contextlib.suppress(Exception):
            await bot.session.close()
        await engine.dispose()


app = FastAPI(title="Milliy sertifikat test bot", lifespan=lifespan, docs_url=None, redoc_url=None)

app.include_router(routes_test.router)
app.include_router(routes_create.router)

app.mount("/app/static", StaticFiles(directory=WEB_DIR / "static"), name="static")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/app/answer")
async def answer_page() -> FileResponse:
    return FileResponse(WEB_DIR / "answer.html")


@app.get("/app/create")
async def create_page() -> FileResponse:
    return FileResponse(WEB_DIR / "create.html")


@app.post("/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request) -> Response:
    """Telegram's update endpoint.

    Always answers 200 once the update is accepted: a non-2xx makes Telegram
    retry the same update, and a handler bug would turn into an endless loop.
    """
    settings = get_settings()
    if secret != settings.webhook_secret:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    bot = request.app.state.bot
    dispatcher = request.app.state.dispatcher

    try:
        update = Update.model_validate(await request.json(), context={"bot": bot})
    except Exception:
        logger.exception("Malformed update payload")
        return Response(status_code=status.HTTP_200_OK)

    try:
        await dispatcher.feed_update(bot, update)
    except Exception:
        logger.exception("Handler raised on update %s", update.update_id)

    return Response(status_code=status.HTTP_200_OK)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Surface API errors in the shape the Mini App expects."""
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
