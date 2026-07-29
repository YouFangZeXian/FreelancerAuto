from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import RuntimeSetting


ALLOWED_RUNTIME_SETTINGS: dict[str, type] = {
    "ai_base_url": str,
    "ai_model": str,
    "ai_timeout_seconds": int,
    "notify_score_threshold": int,
    "scheduler_interval_minutes": int,
    "freelancer_fetch_limit": int,
    "analysis_batch_limit": int,
    "operating_mode": str,
    "starter_review_count": int,
    "starter_completed_projects": int,
}


def get_runtime_settings(db: Session) -> dict[str, str]:
    return {item.key: item.value for item in db.query(RuntimeSetting).all() if item.key in ALLOWED_RUNTIME_SETTINGS}


def update_runtime_settings(db: Session, values: dict[str, Any]) -> None:
    for key, expected_type in ALLOWED_RUNTIME_SETTINGS.items():
        if key not in values:
            continue
        raw = values[key]
        value = str(expected_type(raw))
        row = db.query(RuntimeSetting).filter(RuntimeSetting.key == key).first()
        if row is None:
            db.add(RuntimeSetting(key=key, value=value))
        else:
            row.value = value
    db.commit()


def effective_settings(db: Session, base: Settings) -> Settings:
    raw = get_runtime_settings(db)
    updates: dict[str, Any] = {}
    for key, value in raw.items():
        target = ALLOWED_RUNTIME_SETTINGS[key]
        updates[key] = target(value)
    return base.model_copy(update=updates)
