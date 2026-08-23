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
import re
from contextlib import asynccontextmanager
from pathlib import Path

from aiogram.types import Update
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from app.api import routes_create, routes_test
from app.bot import create_bot, create_dispatcher, set_bot_commands
from app.config import get_settings
from app.store.json_store import init_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent / "web"


async def _supervised_polling(bot, dispatcher) -> None:
    """Keep long polling alive across transient network failures.

    `start_polling` raises out of its task on a dropped connection — which
    happens routinely when a second instance starts and Telegram closes the
    first one's `getUpdates`. Unsupervised, the task dies, nothing notices, and
    the bot goes quiet while the web server keeps answering happily.

    Only relevant to local development; production uses the webhook.
    """
    backoff = 1.0
    while True:
        try:
            await dispatcher.start_polling(bot, handle_signals=False)
            return  # A clean return means someone asked polling to stop.
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Polling stopped unexpectedly; retrying in %.0fs", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)


async def _register_webhook(app: FastAPI, bot, dispatcher, settings) -> None:
    """Register the webhook, retrying until it sticks.

    A single attempt is not enough. Telegram rejects a webhook whose host it
    cannot resolve — a typo in WEBHOOK_BASE, DNS that has not propagated yet, a
    domain added to the site a minute later — and the old behaviour was to log
    the failure once and carry on. The web server then answered `/healthz` with
    200 while the bot received nothing at all, which is the worst possible
    failure shape: healthy-looking and completely dead.

    So: keep trying, and record the outcome where `/healthz` can report it.
    """
    delay = 5.0
    while True:
        try:
            await bot.set_webhook(
                settings.webhook_url,
                drop_pending_updates=True,
                allowed_updates=dispatcher.resolve_used_update_types(),
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            app.state.webhook_ok = False
            app.state.webhook_error = str(error)
            logger.error(
                "Could not register the webhook at %s — retrying in %.0fs. %s",
                settings.webhook_base,
                delay,
                error,
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, 300.0)
            continue

        app.state.webhook_ok = True
        app.state.webhook_error = None
        logger.info("Webhook registered at %s", settings.webhook_url)
        return


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    await init_store(settings.data_dir)

    bot = create_bot()
    dispatcher = create_dispatcher()
    app.state.bot = bot
    app.state.dispatcher = dispatcher
    app.state.webhook_ok = None
    app.state.webhook_error = None

    polling_task: asyncio.Task | None = None
    webhook_task: asyncio.Task | None = None

    try:
        await set_bot_commands(bot)
    except Exception:
        logger.exception("Could not publish the command list")

    if settings.use_polling:
        # Drop any webhook left over from a previous deployment, or Telegram
        # refuses to deliver updates over long polling.
        with contextlib.suppress(Exception):
            await bot.delete_webhook(drop_pending_updates=True)
        polling_task = asyncio.create_task(_supervised_polling(bot, dispatcher))
        logger.info("Bot started in long-polling mode")
    elif settings.webhook_url:
        webhook_task = asyncio.create_task(_register_webhook(app, bot, dispatcher, settings))
    else:
        logger.warning("Neither USE_POLLING nor WEBHOOK_BASE is set; the bot will not receive updates")

    try:
        yield
    finally:
        for task in (polling_task, webhook_task):
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        with contextlib.suppress(Exception):
            await bot.session.close()


app = FastAPI(title="Milliy sertifikat test bot", lifespan=lifespan, docs_url=None, redoc_url=None)

app.include_router(routes_test.router)
app.include_router(routes_create.router)


@app.middleware("http")
async def revalidate_mini_app(request: Request, call_next):
    """Make the Mini App always check back after a deploy.

    Without an explicit Cache-Control, Telegram's in-app browser caches the
    pages heuristically and keeps showing a form long after the server has
    moved on — which reads as "my change did not deploy". `no-cache` still
    allows the cached copy, but every load revalidates against the ETag, so
    updates appear on the very next open at the cost of tiny 304 replies.
    """
    response = await call_next(request)
    if request.url.path.startswith("/app"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/healthz")
async def healthz(request: Request) -> JSONResponse:
    """Health and configuration, diagnosable without SSH.

    Reports whether the bot is actually reachable, not merely whether the web
    server is up — a 200 that says nothing about the bot is how a dead bot went
    unnoticed behind a healthy-looking site.

    Deliberately omits the webhook path: it contains WEBHOOK_SECRET, and this
    endpoint is public. The Mini App base is already public, since it ships
    inside every keyboard button.
    """
    settings = get_settings()
    state = request.app.state

    if settings.use_polling:
        mode = "polling"
        bot_ready = True
    else:
        mode = "webhook"
        bot_ready = bool(getattr(state, "webhook_ok", False))

    body: dict[str, object] = {
        "status": "ok" if bot_ready else "degraded",
        "mode": mode,
        "bot_ready": bot_ready,
        "miniapp_base": settings.miniapp_base or None,
    }

    error = getattr(state, "webhook_error", None)
    if error:
        body["webhook_error"] = error
    if not settings.use_polling and not settings.webhook_base:
        body["webhook_error"] = "WEBHOOK_BASE is not set"

    # 503 so an uptime check notices a bot that cannot receive updates.
    return JSONResponse(body, status_code=200 if bot_ready else 503)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    """Browsers request this unprompted; answering it keeps the logs clean."""
    return FileResponse(WEB_DIR / "static" / "favicon.svg", media_type="image/svg+xml")


_STATIC_REF = re.compile(r'(src|href)="(/app/static/[^"?]+)(\?[^"]*)?"')
_LOCAL_IMPORT = re.compile(r"(from\s+')(/app/static/[A-Za-z0-9_.-]+)(')")
_MEDIA_TYPES = {".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml"}


def _asset_version(path: Path) -> str:
    stat_result = path.stat()
    return f"{int(stat_result.st_mtime):x}-{stat_result.st_size:x}"


def _stamp_static_url(url: str) -> str:
    """Append the file's mtime-size stamp to a `/app/static/...` URL."""
    filename = url.rsplit("/", 1)[-1]
    try:
        version = _asset_version(WEB_DIR / "static" / filename)
    except OSError:
        version = "0"
    return f"{url}?v={version}"


def _versioned_pages_html(name: str) -> HTMLResponse:
    """Serve a Mini App page with version-stamped static asset URLs.

    The keyboard buttons only cache-bust the page itself (`?v=` in
    `miniapp_url`), yet the page pulls its behaviour from `/app/static/*.js`.
    Telegram's in-app browser has been observed serving those subresources from
    its cache after a deploy, so an old script pairs with a new page: buttons
    reference handlers that no longer exist and everything dies silently. Each
    asset URL therefore carries its own file mtime, so any deploy that touches
    a file changes its URL outright and no client can reuse a stale copy.
    """
    html = (WEB_DIR / name).read_text(encoding="utf-8")

    def stamp(match: re.Match[str]) -> str:
        return f'{match.group(1)}="{_stamp_static_url(match.group(2))}"'

    return HTMLResponse(_STATIC_REF.sub(stamp, html))


@app.get("/app/answer")
async def answer_page() -> HTMLResponse:
    return _versioned_pages_html("answer.html")


@app.get("/app/create")
async def create_page() -> HTMLResponse:
    return _versioned_pages_html("create.html")


@app.get("/app/static/{filename}", include_in_schema=False)
async def mini_app_asset(filename: str, request: Request) -> Response:
    """Serve Mini App assets, stamping their internal imports as well.

    Stamping the pages is not enough: a module imports its siblings from inside
    the JS (`from '/app/static/tg.js'`), and that bare URL is exactly where a
    stale cached copy crept back in — new create.js, an old tg.js, and the
    browser rejected the missing export with a dead page. Rewriting those
    imports to carry the same mtime-size stamp makes every edge of the module
    graph change URL whenever any file changes.
    """
    if Path(filename).name != filename:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    path = WEB_DIR / "static" / filename
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    etag = f'"W/{_asset_version(path)}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})

    if path.suffix == ".js":

        def stamp(match: re.Match[str]) -> str:
            return f"{match.group(1)}{_stamp_static_url(match.group(2))}{match.group(3)}"

        body: str | bytes = _LOCAL_IMPORT.sub(stamp, path.read_text(encoding="utf-8"))
    else:
        body = path.read_bytes()

    media_type = _MEDIA_TYPES.get(path.suffix, "application/octet-stream")
    return Response(body, media_type=media_type, headers={"ETag": etag})


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
