from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Project
from app.services.analysis_service import AnalysisService
from app.services.notification_service import NotificationService
from app.services.project_service import ProjectService


class CycleService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def run(self) -> dict[str, object]:
        fetch = ProjectService(self.db, self.settings).fetch_projects()
        analysis = AnalysisService(self.db, self.settings).analyze_pending(limit=self.settings.analysis_batch_limit)
        notified = 0
        for project in self.db.query(Project).filter(Project.status == "analyzed").all():
            if NotificationService(self.db, self.settings).notify_if_eligible(project):
                notified += 1
        return {"fetch": fetch, "analysis": analysis, "notified": notified}
