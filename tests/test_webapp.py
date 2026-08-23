"""The Mini App pages and their static assets.

Telegram's in-app browser caches aggressively, so every URL in the chain —
page, script tags, and the imports modules make from each other — must change
whenever a file changes. These pin that property, plus conditional revalidation.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
import re
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def client(tmp_path):
    from app.main import app
    from app.store.json_store import init_store, reset_store

    await init_store(tmp_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
    reset_store()


def _static_refs(html: str) -> dict[str, str]:
    """Map `/app/static/x.js` -> its `?v=` stamp for every reference."""
    return {
        match.group(1): match.group(2)
        for match in re.finditer(
            r'(?:src|href)="(/app/static/[^"]+)\?v=([0-9a-f]+-[0-9a-f]+)"', html
        )
    }


async def test_pages_stamp_every_static_reference(client):
    """A bare `/app/static/...` reference would let a stale cached copy pair
    with a fresh page — buttons wired to handlers that no longer exist."""
    for page in ("/app/create", "/app/answer"):
        response = await client.get(page)
        assert response.status_code == 200
        refs = _static_refs(response.text)
        assert refs, page
        # Every static reference carries a stamp; nothing slips through bare.
        assert not re.search(r'(?:src|href)="/app/static/[^"?]+"', response.text), page


async def test_js_imports_of_siblings_are_stamped_too(client):
    """The desktop breakage: create.js was fetched fresh while its internal,
    unstamped `from '/app/static/tg.js'` resolved to an old cached copy
    that no longer exported what the new code imports."""
    for page in ("/app/static/create.js", "/app/static/answer.js"):
        response = await client.get(page)
        assert response.status_code == 200
        assert not re.search(r"from '/app/static/tg\.js'", response.text), page
        assert re.search(
            r"from '/app/static/tg\.js\?v=[0-9a-f]+-[0-9a-f]+'", response.text
        ), page


async def test_assets_revalidate_with_etag(client):
    """no-cache + ETag keeps every load honest at the cost of tiny 304s."""
    first = await client.get("/app/static/app.css")
    assert first.status_code == 200
    assert first.headers["cache-control"] == "no-cache"
    etag = first.headers["etag"]

    second = await client.get(
        "/app/static/app.css", headers={"if-none-match": etag}
    )
    assert second.status_code == 304


async def test_unknown_and_traversal_names_are_refused(client):
    assert (await client.get("/app/static/nope.js")).status_code == 404
    assert (await client.get("/app/static/..%2Fmain.py")).status_code in (404, 400)


async def test_javascript_is_served_with_a_strict_content_type(client):
    """Module scripts are rejected outright on a loose MIME type."""
    response = await client.get("/app/static/tg.js")
    assert response.headers["content-type"].startswith("text/javascript")


async def test_pages_are_html_documents(client):
    response = await client.get("/app/create")
    assert response.text.startswith("<!doctype html>")


async def test_the_web_app_bridge_is_self_hosted(client):
    """When telegram.org is unreachable the page used to lose its whole
    session and refuse to save. The bridge script ships with the app now."""
    for page in ("/app/create", "/app/answer"):
        html = (await client.get(page)).text
        assert "telegram.org/js/telegram-web-app.js" not in html, page
        assert '/app/static/telegram-web-app.js' in html, page

    served = await client.get("/app/static/telegram-web-app.js")
    assert served.status_code == 200
    assert "tgWebAppData" in served.text
