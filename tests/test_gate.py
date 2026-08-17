"""Channel-gate enforcement, especially on the API.

The Mini App never touches the bot's dispatcher, so a gate implemented only in
bot handlers lets an unsubscribed user answer tests through the web page. These
tests pin the API side.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.services import channels as channel_service
from tests.test_api import auth_headers, sample_payload


class FakeMember:
    def __init__(self, status: str) -> None:
        self.status = status


class FakeBot:
    """Stands in for aiogram's Bot. `joined` lists the channels the user is in."""

    def __init__(self, joined=(), explode=False) -> None:
        self.joined = set(joined)
        self.explode = explode
        self.calls: list[tuple[str, int]] = []

    async def get_chat_member(self, chat_id, user_id):
        self.calls.append((chat_id, user_id))
        if self.explode:
            raise RuntimeError("telegram unreachable")
        return FakeMember("member" if chat_id in self.joined else "left")

    async def send_message(self, *args, **kwargs):
        return None


@pytest_asyncio.fixture
async def gated(tmp_path):
    from app.main import app
    from app.store.json_store import init_store, reset_store

    store = await init_store(tmp_path)
    await channel_service.add(store, "@kanal_bir")
    await channel_service.add(store, "@kanal_ikki")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, app, store
    reset_store()


@pytest.mark.asyncio
async def test_a_non_member_cannot_read_a_test(gated):
    client, app, _ = gated
    app.state.bot = FakeBot(joined=[])
    response = await client.get("/api/test/777", headers=auth_headers(user_id=50))
    assert response.status_code == 403
    assert "a'zo" in response.json()["error"]


@pytest.mark.asyncio
async def test_partial_membership_is_not_enough(gated):
    """All required channels must be satisfied, not just one."""
    client, app, _ = gated
    app.state.bot = FakeBot(joined=["@kanal_bir"])
    response = await client.get("/api/test/777", headers=auth_headers(user_id=51))
    assert response.status_code == 403
    assert "@kanal_ikki" in response.json()["error"]
    assert "@kanal_bir" not in response.json()["error"]


@pytest.mark.asyncio
async def test_a_non_member_cannot_submit_answers(gated):
    """The one that matters: this is the request carrying the answers."""
    client, app, _ = gated
    app.state.bot = FakeBot(joined=["@kanal_bir", "@kanal_ikki"])
    await client.post("/api/test", json=sample_payload("777"), headers=auth_headers(user_id=1))

    app.state.bot = FakeBot(joined=[])
    response = await client.post(
        "/api/attempt",
        json={"code": "777", "answers": {"1": "A"}},
        headers=auth_headers(user_id=52),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_a_non_member_cannot_create_a_test(gated):
    client, app, _ = gated
    app.state.bot = FakeBot(joined=[])
    response = await client.post(
        "/api/test", json=sample_payload("778"), headers=auth_headers(user_id=53)
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_a_full_member_is_allowed_through(gated):
    client, app, _ = gated
    app.state.bot = FakeBot(joined=["@kanal_bir", "@kanal_ikki"])
    created = await client.post(
        "/api/test", json=sample_payload("779"), headers=auth_headers(user_id=54)
    )
    assert created.status_code == 201

    fetched = await client.get("/api/test/779", headers=auth_headers(user_id=54))
    assert fetched.status_code == 200


@pytest.mark.asyncio
async def test_the_check_fails_closed_when_telegram_is_unreachable(gated):
    """A bot removed as channel admin must not silently disable the gate."""
    client, app, _ = gated
    app.state.bot = FakeBot(explode=True)
    response = await client.get("/api/test/777", headers=auth_headers(user_id=55))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_no_configured_channels_means_no_gate(tmp_path):
    from app.main import app
    from app.store.json_store import init_store, reset_store

    await init_store(tmp_path)
    app.state.bot = FakeBot(joined=[])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/test", json=sample_payload("780"), headers=auth_headers(user_id=56)
        )
        assert created.status_code == 201
    reset_store()


@pytest.mark.asyncio
async def test_membership_is_rechecked_on_every_call(gated):
    """Leaving the channel must take effect immediately, not at next login."""
    client, app, _ = gated
    app.state.bot = FakeBot(joined=["@kanal_bir", "@kanal_ikki"])
    assert (await client.get("/api/test/777", headers=auth_headers(user_id=57))).status_code == 404

    app.state.bot = FakeBot(joined=["@kanal_bir"])
    assert (await client.get("/api/test/777", headers=auth_headers(user_id=57))).status_code == 403
