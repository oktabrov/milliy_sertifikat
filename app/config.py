"""Runtime configuration, read from the environment or a local .env file."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.scoring.scenarios import BallScale


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str

    # Public HTTPS origin, e.g. https://youraccount.alwaysdata.net
    # Telegram requires HTTPS for both the webhook and the Mini App.
    webhook_base: str = ""
    webhook_secret: str = "change-me"

    # Long polling is for local development only; alwaysdata runs the webhook.
    use_polling: bool = False

    # Directory holding users.json, tests.json and attempts.json.
    data_dir: str = "./data"

    # Comma-separated Telegram user ids.
    admin_ids: str = ""
    # Comma-separated @usernames a student must join before answering.
    required_channels: str = ""

    help_video_url: str = ""
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
        out = []
        for chunk in self.admin_ids.split(","):
            chunk = chunk.strip()
            if chunk.lstrip("-").isdigit():
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
