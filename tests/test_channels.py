"""Required-channel management: none, one, or many."""

from __future__ import annotations

import pytest

from app.config import DEFAULT_ADMIN_IDS, Settings
from app.services import channels as channel_service
from app.store.json_store import Store


@pytest.fixture
async def store(tmp_path) -> Store:
    instance = Store(tmp_path)
    await instance.load()
    return instance


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("@fizika_kanal", "@fizika_kanal"),
        ("fizika_kanal", "@fizika_kanal"),
        ("t.me/fizika_kanal", "@fizika_kanal"),
        ("https://t.me/fizika_kanal", "@fizika_kanal"),
        ("https://t.me/fizika_kanal/", "@fizika_kanal"),
        ("  @fizika_kanal  ", "@fizika_kanal"),
        ("-1001234567890", "-1001234567890"),
    ],
)
def test_normalize_accepts_the_shapes_people_actually_paste(raw, expected):
    assert channel_service.normalize(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "@ab", "not a channel!", "https://example.com/x", "-100"])
def test_normalize_rejects_nonsense(raw):
    with pytest.raises(channel_service.ChannelError):
        channel_service.normalize(raw)


@pytest.mark.asyncio
async def test_none_one_and_many(store: Store):
    assert channel_service.current(store) == []

    channels, added = await channel_service.add(store, "@kanal_one")
    assert added == "@kanal_one"
    assert channels == ["@kanal_one"]

    channels, _ = await channel_service.add(store, "t.me/kanal_two")
    channels, _ = await channel_service.add(store, "-1001234567890")
    assert channels == ["@kanal_one", "@kanal_two", "-1001234567890"]

    channels, removed = await channel_service.remove(store, "@kanal_two")
    assert removed is True
    assert channels == ["@kanal_one", "-1001234567890"]


@pytest.mark.asyncio
async def test_adding_the_same_channel_twice_is_a_no_op(store: Store):
    await channel_service.add(store, "@kanal_one")
    channels, _ = await channel_service.add(store, "@KANAL_ONE")
    assert channels == ["@kanal_one"]


@pytest.mark.asyncio
async def test_removing_something_absent_reports_it(store: Store):
    await channel_service.add(store, "@kanal_one")
    channels, removed = await channel_service.remove(store, "@kanal_other")
    assert removed is False
    assert channels == ["@kanal_one"]


@pytest.mark.asyncio
async def test_the_list_survives_a_restart(store: Store, tmp_path):
    await channel_service.add(store, "@kanal_one")
    await channel_service.add(store, "@kanal_two")

    reopened = Store(tmp_path)
    await reopened.load()
    assert channel_service.current(reopened) == ["@kanal_one", "@kanal_two"]


@pytest.mark.asyncio
async def test_clearing_means_no_gate_not_fall_back_to_env(store: Store, tmp_path, monkeypatch):
    """The subtle one.

    REQUIRED_CHANNELS seeds the list only while it has never been configured.
    Once an admin empties it, an empty list must stick — otherwise removing the
    last channel would silently restore whatever .env says.
    """
    monkeypatch.setattr(
        channel_service,
        "get_settings",
        lambda: Settings(bot_token="t:1", required_channels="@kanal_from_env"),
    )
    assert channel_service.current(store) == ["@kanal_from_env"]

    await channel_service.clear(store)
    assert channel_service.current(store) == []

    reopened = Store(tmp_path)
    await reopened.load()
    assert channel_service.current(reopened) == []


@pytest.mark.asyncio
async def test_removing_the_last_channel_also_sticks(store: Store, monkeypatch):
    monkeypatch.setattr(
        channel_service,
        "get_settings",
        lambda: Settings(bot_token="t:1", required_channels="@kanal_from_env"),
    )
    await channel_service.add(store, "@kanal_added")
    channels, _ = await channel_service.remove(store, "@kanal_from_env")
    channels, _ = await channel_service.remove(store, "@kanal_added")
    assert channels == []
    assert channel_service.current(store) == []


def test_the_default_admin_is_always_present():
    """With no ADMIN_IDS at all, somebody must still be able to run /kanallar."""
    assert 5736677391 in DEFAULT_ADMIN_IDS
    assert Settings(bot_token="t:1").admin_id_list == [5736677391]


def test_admin_ids_add_to_the_default_rather_than_replacing_it():
    settings = Settings(bot_token="t:1", admin_ids="111, 222")
    assert settings.admin_id_list == [5736677391, 111, 222]


def test_the_default_admin_is_not_duplicated():
    settings = Settings(bot_token="t:1", admin_ids="5736677391,111")
    assert settings.admin_id_list == [5736677391, 111]


@pytest.mark.asyncio
async def test_admin_flag_is_refreshed_on_later_contact(store: Store):
    """A user created before being promoted must not keep the stale flag."""
    user = await store.ensure_user(999, is_admin=False)
    assert user.is_admin is False

    refreshed = await store.ensure_user(999, is_admin=True)
    assert refreshed.is_admin is True
    assert store.get_user(999).is_admin is True
