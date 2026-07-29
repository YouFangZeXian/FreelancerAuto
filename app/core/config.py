from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Secrets are loaded only from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_base_url: str = "http://localhost:8000"
    database_url: str = "sqlite:///./data/freelancer_auto.db"
    log_level: str = "INFO"
    scheduler_interval_minutes: int = Field(default=10, ge=1, le=1440)
    enable_scheduler: bool = False

    freelancer_mock_mode: bool = True
    freelancer_base_url: str = "https://www.freelancer.com"
    freelancer_access_token: str = ""
    freelancer_bidder_id: int | None = None
    freelancer_bid_submission_enabled: bool = False
    freelancer_fetch_limit: int = Field(default=300, ge=1, le=1000)
    analysis_batch_limit: int = Field(default=300, ge=1, le=1000)

    # Operational strategy. Runtime values can be changed from the project page.
    operating_mode: str = "starter"
    starter_review_count: int = Field(default=0, ge=0)
    starter_completed_projects: int = Field(default=0, ge=0)

    ai_base_url: str = ""
    ai_api_key: str = ""
    ai_model: str = ""
    ai_timeout_seconds: int = Field(default=90, ge=5, le=600)
    ai_max_retries: int = Field(default=3, ge=0, le=8)
    ai_dry_run: bool = True

    ntfy_base_url: str = "https://ntfy.sh"
    ntfy_topic: str = ""
    ntfy_token: str = ""
    notify_score_threshold: int = Field(default=70, ge=0, le=100)

    max_bids_per_hour: int = Field(default=2, ge=1, le=100)
    max_bids_per_day: int = Field(default=8, ge=1, le=500)

    filters_path: Path = Path("config/filters.yaml")
    profile_path: Path = Path("config/profile.yaml")

    @property
    def freelancer_api_url(self) -> str:
        return f"{self.freelancer_base_url.rstrip('/')}/api"

    @property
    def is_freelancer_configured(self) -> bool:
        return self.freelancer_mock_mode or bool(self.freelancer_access_token)

    @property
    def is_ai_configured(self) -> bool:
        return self.ai_dry_run or bool(self.ai_base_url and self.ai_api_key and self.ai_model)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
