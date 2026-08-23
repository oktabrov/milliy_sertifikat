"""Runtime configuration, read from the environment or a local .env file.

Deliberately hand-rolled rather than pydantic-settings: this is thirty lines of
parsing against a 296 KB dependency, and pydantic itself is already in the tree
only because aiogram requires it.

Precedence is real environment variables first, then `.env`, then the default.
The check is `in`, not truthiness — an explicitly empty `WEBHOOK_BASE=` must
override a value in `.env`, which a simple `or` chain would silently ignore.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.scoring.scenarios import BallScale

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off", ""}

# Always an admin, whatever ADMIN_IDS says. ADMIN_IDS adds to this, never
# replaces it, so the bot can never end up with no administrator at all.
DEFAULT_ADMIN_IDS: tuple[int, ...] = (5736677391,)


def _read_env_file(path: Path) -> dict[str, str]:
    """Parse a `.env` file: KEY=value, `#` comments, optional surrounding quotes."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return values

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            values[key] = value
    return values


class _Source:
    def __init__(self, env_file: Path) -> None:
        self._file = _read_env_file(env_file)

    def raw(self, key: str) -> str | None:
        if key in os.environ:
            return os.environ[key]
        if key in self._file:
            return self._file[key]
        return None

    def text(self, key: str, default: str) -> str:
        value = self.raw(key)
        return default if value is None else value

    def flag(self, key: str, default: bool) -> bool:
        value = self.raw(key)
        if value is None:
            return default
        lowered = value.strip().lower()
        if lowered in _TRUTHY:
            return True
        if lowered in _FALSY:
            return False
        return default

    def number(self, key: str, default: int) -> int:
        value = self.raw(key)
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return default

    def decimal(self, key: str, default: float) -> float:
        value = self.raw(key)
        try:
            return float(str(value).strip())
        except (TypeError, ValueError):
            return default


@dataclass(frozen=True)
class Settings:
    bot_token: str

    # Public HTTPS origin, e.g. https://youraccount.alwaysdata.net
    # Telegram requires HTTPS for both the webhook and the Mini App.
    webhook_base: str = ""
    webhook_secret: str = "change-me"

    # Long polling is for local development only; alwaysdata runs the webhook.
    use_polling: bool = False

    # Directory holding users.json, tests.json and attempts.json.
    data_dir: str = "./data"

    admin_ids: str = ""
    required_channels: str = ""

    help_video_url: str = ""
    help_video_file_id: str = ""
    support_username: str = ""

    # Re-calibrate item difficulty from real responses once this many students
    # have submitted. Below it, the default difficulty profile is used.
    min_real_submissions: int = 20
    cohort_size: int = 10_000

    ball_midpoint: float = 50.0
    ball_slope: float = 16.0
    # "70:A+,65:A,..." highest threshold first.
    ball_bands: str = "70:A+,65:A,60:B+,55:B,50:C+,46:C"

    @property
    def admin_id_list(self) -> list[int]:
        """Admins, always including the built-in owner.

        Without a default, an empty ADMIN_IDS would leave nobody able to run
        /kanallar — and no way to fix it except editing .env and restarting.
        """
        out = list(DEFAULT_ADMIN_IDS)
        for chunk in self.admin_ids.split(","):
            chunk = chunk.strip()
            if chunk.lstrip("-").isdigit() and int(chunk) not in out:
                out.append(int(chunk))
        return out

    @property
    def required_channel_list(self) -> list[str]:
        out = []
        for chunk in self.required_channels.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            out.append(chunk if chunk.startswith("@") or chunk.startswith("-") else f"@{chunk}")
        return out

    @property
    def webhook_path(self) -> str:
        return f"/webhook/{self.webhook_secret}"

    @property
    def webhook_url(self) -> str:
        return f"{self.webhook_base.rstrip('/')}{self.webhook_path}" if self.webhook_base else ""

    @property
    def miniapp_base(self) -> str:
        return f"{self.webhook_base.rstrip('/')}/app" if self.webhook_base else ""

    @property
    def ball_scale(self) -> BallScale:
        bands: list[tuple[int, str]] = []
        for chunk in self.ball_bands.split(","):
            chunk = chunk.strip()
            if ":" not in chunk:
                continue
            threshold, label = chunk.split(":", 1)
            if threshold.strip().isdigit():
                bands.append((int(threshold.strip()), label.strip()))
        bands.sort(key=lambda pair: pair[0], reverse=True)
        return BallScale(
            midpoint=self.ball_midpoint,
            slope=self.ball_slope,
            bands=tuple(bands) or BallScale().bands,
        )


def load_settings(env_file: Path | None = None) -> Settings:
    source = _Source(env_file or ENV_FILE)

    bot_token = source.text("BOT_TOKEN", "")
    if not bot_token:
        # Fail at startup rather than on the first Telegram call, so a
        # half-configured deployment never looks healthy.
        raise RuntimeError("BOT_TOKEN is not set (put it in .env or the environment)")

    return Settings(
        bot_token=bot_token,
        webhook_base=source.text("WEBHOOK_BASE", ""),
        webhook_secret=source.text("WEBHOOK_SECRET", "change-me"),
        use_polling=source.flag("USE_POLLING", False),
        data_dir=source.text("DATA_DIR", "./data"),
        admin_ids=source.text("ADMIN_IDS", ""),
        required_channels=source.text("REQUIRED_CHANNELS", ""),
        help_video_url=source.text("HELP_VIDEO_URL", ""),
        help_video_file_id=source.text("HELP_VIDEO_FILE_ID", ""),
        support_username=source.text("SUPPORT_USERNAME", ""),
        min_real_submissions=source.number("MIN_REAL_SUBMISSIONS", 20),
        cohort_size=source.number("COHORT_SIZE", 10_000),
        ball_midpoint=source.decimal("BALL_MIDPOINT", 50.0),
        ball_slope=source.decimal("BALL_SLOPE", 16.0),
        ball_bands=source.text("BALL_BANDS", "70:A+,65:A,60:B+,55:B,50:C+,46:C"),
    )


@lru_cache
def get_settings() -> Settings:
    return load_settings()
