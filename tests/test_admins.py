"""Administrator management."""

from __future__ import annotations

import pytest

from app.config import DEFAULT_ADMIN_IDS, Settings
from app.services import admins as admin_service
from app.store.json_store import Store

OWNER = DEFAULT_ADMIN_IDS[0]


@pytest.fixture
async def store(tmp_path) -> Store:
    instance = Store(tmp_path)
    await instance.load()
    return instance


@pytest.mark.asyncio
async def test_the_owner_is_an_admin_out_of_the_box(store: Store):
    assert admin_service.current_ids(store) == [OWNER]
    assert admin_service.is_admin(store, OWNER) is True
    assert admin_service.is_admin(store, 12345) is False


@pytest.mark.asyncio
async def test_adding_and_removing_at_runtime(store: Store):
    ids, added = await admin_service.add(store, 12345)
    assert added is True
    assert ids == [OWNER, 12345]
    assert admin_service.is_admin(store, 12345) is True

    ids, removed = await admin_service.remove(store, 12345)
    assert removed is True
    assert ids == [OWNER]
    assert admin_service.is_admin(store, 12345) is False


@pytest.mark.asyncio
async def test_adding_twice_changes_nothing(store: Store):
    await admin_service.add(store, 12345)
    ids, added = await admin_service.add(store, 12345)
    assert added is False
    assert ids == [OWNER, 12345]


@pytest.mark.asyncio
async def test_removing_someone_who_is_not_an_admin(store: Store):
    ids, removed = await admin_service.remove(store, 999)
    assert removed is False
    assert ids == [OWNER]


@pytest.mark.asyncio
async def test_the_owner_can_never_be_removed(store: Store):
    """Otherwise the bot can be left with nobody able to administer it."""
    ids, removed = await admin_service.remove(store, OWNER)
    assert removed is False
    assert OWNER in ids
    assert admin_service.is_admin(store, OWNER) is True


@pytest.mark.asyncio
async def test_admins_survive_a_restart(store: Store, tmp_path):
    await admin_service.add(store, 555)
    reopened = Store(tmp_path)
    await reopened.load()
    assert admin_service.is_admin(reopened, 555) is True


@pytest.mark.asyncio
async def test_environment_admins_are_included_and_not_removable(store: Store, monkeypatch):
    monkeypatch.setattr(
        admin_service, "get_settings", lambda: Settings(bot_token="t:1", admin_ids="777")
    )
    assert admin_service.is_admin(store, 777) is True
    assert admin_service.origin(store, 777) == "env"

    ids, removed = await admin_service.remove(store, 777)
    assert removed is False
    assert 777 in ids


@pytest.mark.asyncio
async def test_origin_labels(store: Store):
    await admin_service.add(store, 4242)
    assert admin_service.origin(store, OWNER) == "owner"
    assert admin_service.origin(store, 4242) == "runtime"


@pytest.mark.asyncio
async def test_corrupt_stored_ids_are_ignored(store: Store):
    await store.set_setting(admin_service.SETTING_KEY, [111, "222", None, "abc", {}])
    assert admin_service.stored_ids(store) == [111, 222]


@pytest.mark.asyncio
async def test_the_middleware_sees_a_runtime_admin(store: Store):
    """A newly added admin must be recognised without editing .env."""
    user = await store.ensure_user(8888, is_admin=admin_service.is_admin(store, 8888))
    assert user.is_admin is False

    await admin_service.add(store, 8888)
    refreshed = await store.ensure_user(8888, is_admin=admin_service.is_admin(store, 8888))
    assert refreshed.is_admin is True
