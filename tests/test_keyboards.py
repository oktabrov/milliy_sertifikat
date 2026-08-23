"""Keyboards and router ordering.

The Mini App URL is frozen into a reply-keyboard button when it is sent, so
what `ms_keyboard` builds *now* is what a user is stuck with until the keyboard
is replaced. These pin that behaviour.
"""

from __future__ import annotations

import pytest

from app.bot import create_dispatcher, keyboards
from app.config import Settings


def settings_with(**overrides) -> Settings:
    base = {"bot_token": "123456:test-token-not-real"}
    base.update(overrides)
    return Settings(**base)


def buttons(markup):
    return [button for row in markup.keyboard for button in row]


def test_https_base_produces_mini_app_buttons(monkeypatch):
    monkeypatch.setattr(
        keyboards,
        "get_settings",
        lambda: settings_with(webhook_base="https://umrbek1.alwaysdata.net"),
    )
    found = {button.text: button for button in buttons(keyboards.ms_keyboard())}

    assert found["Test tekshirish"].web_app is not None
    assert found["Test yaratish"].web_app is not None
    assert found["Test tekshirish"].web_app.url == "https://umrbek1.alwaysdata.net/app/answer"
    assert found["Test yaratish"].web_app.url == "https://umrbek1.alwaysdata.net/app/create"
    # These two are ordinary buttons; the bot answers them itself.
    assert found["Mening natijalarim"].web_app is None
    assert found["Mening testlarim"].web_app is None


def test_a_trailing_slash_does_not_double_up(monkeypatch):
    monkeypatch.setattr(
        keyboards, "get_settings", lambda: settings_with(webhook_base="https://x.test/")
    )
    found = {button.text: button for button in buttons(keyboards.ms_keyboard())}
    assert found["Test tekshirish"].web_app.url == "https://x.test/app/answer"


@pytest.mark.parametrize("base", ["", "http://insecure.test"])
def test_a_non_https_base_yields_plain_buttons(monkeypatch, base):
    """Telegram silently drops web_app buttons that are not HTTPS.

    Building one anyway gives the user a button that does nothing at all, so the
    keyboard degrades to plain buttons and the handler explains instead.
    """
    monkeypatch.setattr(keyboards, "get_settings", lambda: settings_with(webhook_base=base))
    for button in buttons(keyboards.ms_keyboard()):
        assert button.web_app is None


def test_the_intro_buttons_live_in_the_reply_keyboard():
    """/start must need only one message: a message can carry either inline or
    reply markup, so keeping the intro buttons inline meant a second bubble."""
    found = {button.text for button in buttons(keyboards.ms_keyboard())}
    assert keyboards.texts.BTN_HOW_TO_ANSWER in found
    assert keyboards.texts.BTN_HOW_TO_CREATE in found
    assert keyboards.texts.BTN_HELP_VIDEO in found


def test_the_fallback_router_is_registered_last():
    """It claims any unmatched text. Registered earlier, it would swallow
    name registration and every button the other routers handle."""
    names = [router.name for router in create_dispatcher().sub_routers]
    assert names[-1] == "fallback"
    assert names.index("start") < names.index("fallback")
    assert names.index("ms") < names.index("fallback")
    assert names.index("admin") < names.index("fallback")
