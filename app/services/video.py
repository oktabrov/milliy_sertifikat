"""The video behind the "Botda test ishlash va yaratish(+video)" button.

Two shapes are supported, mirroring the .env options:

- a Telegram file_id — the button sends the video itself into the chat
- an https link (YouTube, Drive, …) — the button becomes a URL button

Values live in settings.json, so admins manage them with /video and
/video_ochirish instead of editing the deployment. A value stored at runtime
wins over .env even when empty: removing the video must not silently
resurrect whatever HELP_VIDEO_* says in .env.
"""

from __future__ import annotations

from app.config import get_settings
from app.store.json_store import Store

URL_KEY = "help_video_url"
FILE_ID_KEY = "help_video_file_id"


def current(store: Store) -> tuple[str, str]:
    """Effective (url, file_id). Runtime settings first; a link beats a file."""
    settings = get_settings()
    url = str(store.get_setting(URL_KEY, settings.help_video_url) or "").strip()
    file_id = str(store.get_setting(FILE_ID_KEY, settings.help_video_file_id) or "").strip()
    return url, file_id


async def set_url(store: Store, url: str) -> None:
    await store.set_setting(URL_KEY, url)
    await store.set_setting(FILE_ID_KEY, "")


async def set_file_id(store: Store, file_id: str) -> None:
    await store.set_setting(FILE_ID_KEY, file_id)
    await store.set_setting(URL_KEY, "")


async def clear(store: Store) -> None:
    await store.set_setting(URL_KEY, "")
    await store.set_setting(FILE_ID_KEY, "")
