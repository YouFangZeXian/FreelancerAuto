from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import Settings
from app.db.session import SessionLocal
from app.services.cycle_service import CycleService
from app.services.runtime_settings import effective_settings

logger = logging.getLogger(__name__)


def run_scheduled_cycle(base_settings: Settings) -> None:
    with SessionLocal() as db:
        try:
            result = CycleService(db, effective_settings(db, base_settings)).run()
            logger.info("scheduled cycle complete: %s", result)
        except Exception:
            logger.exception("scheduled cycle failed")


def build_scheduler(settings: Settings) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        run_scheduled_cycle,
        "interval",
        minutes=settings.scheduler_interval_minutes,
        args=[settings],
        id="freelancer-project-cycle",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    return scheduler

