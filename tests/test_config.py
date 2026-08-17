"""Configuration loading — precedence and coercion."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.config import _read_env_file, load_settings


def write_env(tmp_path: Path, body: str) -> Path:
    path = tmp_path / ".env"
    path.write_text(body, encoding="utf-8")
    return path


def test_parses_comments_blanks_and_quotes(tmp_path: Path):
    path = write_env(
        tmp_path,
        "\n# a comment\nBOT_TOKEN=abc:123\n\nWEBHOOK_BASE='https://x.test'\n"
        'WEBHOOK_SECRET="quoted"\nnot a pair\n',
    )
    values = _read_env_file(path)
    assert values["BOT_TOKEN"] == "abc:123"
    assert values["WEBHOOK_BASE"] == "https://x.test"
    assert values["WEBHOOK_SECRET"] == "quoted"
    assert "not a pair" not in values


def test_values_come_from_the_env_file(tmp_path: Path, monkeypatch):
    for key in ("BOT_TOKEN", "COHORT_SIZE", "USE_POLLING", "WEBHOOK_BASE"):
        monkeypatch.delenv(key, raising=False)
    path = write_env(tmp_path, "BOT_TOKEN=t:1\nCOHORT_SIZE=250\nUSE_POLLING=true\n")
    settings = load_settings(path)
    assert settings.bot_token == "t:1"
    assert settings.cohort_size == 250
    assert settings.use_polling is True


def test_real_environment_outranks_the_env_file(tmp_path: Path, monkeypatch):
    path = write_env(tmp_path, "BOT_TOKEN=from-file\n")
    monkeypatch.setenv("BOT_TOKEN", "from-environment")
    assert load_settings(path).bot_token == "from-environment"


def test_an_explicitly_empty_variable_overrides_the_file(tmp_path: Path, monkeypatch):
    """The bug a naive `or` chain would introduce.

    A test run sets WEBHOOK_BASE= to disable Mini App buttons; that must win
    over a developer's populated .env, not fall through to it.
    """
    path = write_env(tmp_path, "BOT_TOKEN=t:1\nWEBHOOK_BASE=https://leaked.test\n")
    monkeypatch.setenv("WEBHOOK_BASE", "")
    assert load_settings(path).webhook_base == ""


def test_a_missing_token_fails_loudly(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    path = write_env(tmp_path, "WEBHOOK_BASE=https://x.test\n")
    with pytest.raises(RuntimeError, match="BOT_TOKEN"):
        load_settings(path)


@pytest.mark.parametrize(
    ("written", "expected"),
    [("true", True), ("True", True), ("1", True), ("yes", True), ("on", True),
     ("false", False), ("0", False), ("no", False), ("", False), ("nonsense", False)],
)
def test_boolean_coercion(tmp_path: Path, monkeypatch, written, expected):
    monkeypatch.delenv("USE_POLLING", raising=False)
    path = write_env(tmp_path, f"BOT_TOKEN=t:1\nUSE_POLLING={written}\n")
    assert load_settings(path).use_polling is expected


def test_bad_numbers_fall_back_to_the_default(tmp_path: Path, monkeypatch):
    for key in ("COHORT_SIZE", "BALL_SLOPE"):
        monkeypatch.delenv(key, raising=False)
    path = write_env(tmp_path, "BOT_TOKEN=t:1\nCOHORT_SIZE=abc\nBALL_SLOPE=xyz\n")
    settings = load_settings(path)
    assert settings.cohort_size == 10_000
    assert settings.ball_slope == 16.0


def test_a_missing_env_file_is_not_an_error(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "t:1")
    monkeypatch.delenv("DATA_DIR", raising=False)
    settings = load_settings(tmp_path / "nope.env")
    assert settings.bot_token == "t:1"
    assert settings.data_dir == "./data"


def test_derived_properties(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("WEBHOOK_BASE", raising=False)
    monkeypatch.delenv("ADMIN_IDS", raising=False)
    monkeypatch.delenv("REQUIRED_CHANNELS", raising=False)
    path = write_env(
        tmp_path,
        "BOT_TOKEN=t:1\nWEBHOOK_BASE=https://x.test/\nWEBHOOK_SECRET=s3cret\n"
        "ADMIN_IDS=1, 2 ,bad,3\nREQUIRED_CHANNELS=one, @two\n",
    )
    settings = load_settings(path)
    assert settings.webhook_url == "https://x.test/webhook/s3cret"
    assert settings.miniapp_base == "https://x.test/app"
    assert settings.admin_id_list == [1, 2, 3]
    assert settings.required_channel_list == ["@one", "@two"]


def test_ball_scale_is_parsed_and_sorted(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("BALL_BANDS", raising=False)
    path = write_env(tmp_path, "BOT_TOKEN=t:1\nBALL_BANDS=50:C+,70:A+,65:A\n")
    scale = load_settings(path).ball_scale
    assert scale.grade(71) == "A+"
    assert scale.grade(66) == "A"
    assert scale.grade(51) == "C+"


def test_a_malformed_band_string_falls_back(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("BALL_BANDS", raising=False)
    path = write_env(tmp_path, "BOT_TOKEN=t:1\nBALL_BANDS=garbage\n")
    assert load_settings(path).ball_scale.grade(95) == "A+"
