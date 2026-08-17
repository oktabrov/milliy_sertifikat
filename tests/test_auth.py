"""Mini App initData verification.

These are the tests that matter most for safety: the HMAC is the only thing
stopping anyone from submitting answers as another student.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from app.api.auth import InitDataError, verify_init_data

TOKEN = "123456:test-token-not-real"


def make_init_data(user: dict | None = None, auth_date: int | None = None, token: str = TOKEN) -> str:
    fields = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAF_test",
        "user": json.dumps(user or {"id": 42, "first_name": "Sardor", "last_name": "Torayev"}),
    }
    check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_accepts_a_correctly_signed_payload():
    user = verify_init_data(make_init_data(), TOKEN)
    assert user.id == 42
    assert user.full_name == "Sardor Torayev"


def test_rejects_a_tampered_user_id():
    """The attack this whole mechanism exists to stop."""
    signed = make_init_data({"id": 42, "first_name": "Sardor"})
    forged = signed.replace("42", "99")
    with pytest.raises(InitDataError):
        verify_init_data(forged, TOKEN)


def test_rejects_a_payload_signed_with_another_token():
    with pytest.raises(InitDataError):
        verify_init_data(make_init_data(token="999:someone-elses-bot"), TOKEN)


def test_rejects_a_missing_hash():
    fields = {"auth_date": str(int(time.time())), "user": json.dumps({"id": 1})}
    with pytest.raises(InitDataError):
        verify_init_data(urlencode(fields), TOKEN)


def test_rejects_empty_init_data():
    with pytest.raises(InitDataError):
        verify_init_data("", TOKEN)


def test_rejects_stale_init_data():
    stale = make_init_data(auth_date=int(time.time()) - 7200)
    with pytest.raises(InitDataError):
        verify_init_data(stale, TOKEN, max_age_seconds=3600)


def test_accepts_stale_init_data_when_the_age_check_is_disabled():
    stale = make_init_data(auth_date=int(time.time()) - 7200)
    assert verify_init_data(stale, TOKEN, max_age_seconds=0).id == 42


def test_rejects_a_payload_with_no_user():
    fields = {"auth_date": str(int(time.time()))}
    check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    with pytest.raises(InitDataError):
        verify_init_data(urlencode(fields), TOKEN)


def test_full_name_handles_a_missing_surname():
    user = verify_init_data(make_init_data({"id": 7, "first_name": "Ali"}), TOKEN)
    assert user.full_name == "Ali"
