from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import init_db
from app.tasks.scheduler import build_scheduler
from app.web import router as web_router


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        Path("data").mkdir(parents=True, exist_ok=True)
        init_db()
        scheduler = None
        if settings.enable_scheduler:
            scheduler = build_scheduler(settings)
            scheduler.start()
        try:
            yield
        finally:
            if scheduler:
                scheduler.shutdown(wait=False)

    app = FastAPI(title="FreelancerAuto", version="1.0.0", lifespan=lifespan)
    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.include_router(api_router)
    app.include_router(web_router)
    return app


app = create_app()

