from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.base import Base
from app.models import entities  # noqa: F401


@pytest.fixture()
def db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _record):  # type: ignore[no-untyped-def]
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    filters = tmp_path / "filters.yaml"
    filters.write_text(
        """include_keywords:\n  - python\n  - fastapi\n  - automation\n  - api\nexclude_keywords:\n  - academic cheating\n  - captcha\nmin_budget_usd: 30\nmax_budget_usd: 2000\nmax_existing_bids: 50\nmin_employer_rating: 3.5\nrequire_payment_verified: false\nallowed_project_types:\n  - fixed\n  - hourly\n""",
        encoding="utf-8",
    )
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        """skills:\n  - Python\n  - FastAPI\n  - API integration\npreferences:\n  preferred_projects:\n    - Automation\n  avoid_projects:\n    - Illegal work\npricing:\n  target_hourly_rate_usd: 20\n  minimum_effective_hourly_rate_usd: 10\navailability:\n  max_active_projects: 2\n  available_hours_per_week: 20\n""",
        encoding="utf-8",
    )
    return Settings(
        _env_file=None,
        database_url="sqlite://",
        filters_path=filters,
        profile_path=profile,
        freelancer_mock_mode=True,
        ai_dry_run=True,
        ntfy_topic="",
    )

