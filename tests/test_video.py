"""The intro video behind the (+video) button: runtime settings vs .env."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.services import video as video_service
from app.store.json_store import Store


@pytest.fixture
async def store(tmp_path) -> Store:
    instance = Store(tmp_path)
    await instance.load()
    return instance


def env_with(**overrides) -> Settings:
    base = {"bot_token": "t:1"}
    base.update(overrides)
    return Settings(**base)


@pytest.mark.asyncio
async def test_with_nothing_configured_the_env_values_apply(store: Store, monkeypatch):
    monkeypatch.setattr(
        video_service,
        "get_settings",
        lambda: env_with(help_video_url="https://youtu.be/x", help_video_file_id="FILE"),
    )
    assert video_service.current(store) == ("https://youtu.be/x", "FILE")


@pytest.mark.asyncio
async def test_storing_a_video_survives_a_restart(store: Store, tmp_path):
    await video_service.set_file_id(store, "VIDEO-123")

    reopened = Store(tmp_path)
    await reopened.load()
    url, file_id = video_service.current(reopened)
    assert file_id == "VIDEO-123"
    assert url == ""


@pytest.mark.asyncio
async def test_a_link_beats_a_stored_video_and_vice_versa(store: Store):
    await video_service.set_file_id(store, "VIDEO-123")
    await video_service.set_url(store, "https://youtu.be/y")
    _, file_id = video_service.current(store)
    assert file_id == ""

    await video_service.set_file_id(store, "VIDEO-456")
    url, _ = video_service.current(store)
    assert url == ""


@pytest.mark.asyncio
async def test_removing_means_gone_not_fall_back_to_env(store: Store, tmp_path, monkeypatch):
    """The subtle one.

    An admin who runs /video_ochirish wants no video. If clearing restored
    whatever HELP_VIDEO_* says in .env, removal would look broken while every
    student still got the old clip.
    """
    monkeypatch.setattr(
        video_service,
        "get_settings",
        lambda: env_with(help_video_url="https://youtu.be/env"),
    )
    assert video_service.current(store)[0] == "https://youtu.be/env"

    await video_service.clear(store)
    assert video_service.current(store) == ("", "")

    reopened = Store(tmp_path)
    await reopened.load()
    assert video_service.current(reopened) == ("", "")
