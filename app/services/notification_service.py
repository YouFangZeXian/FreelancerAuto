from __future__ import annotations

from sqlalchemy.orm import Session

from app.clients.ntfy import NtfyClient
from app.core.config import Settings
from app.models import Notification, Project
from app.services.audit_service import audit


class NotificationService:
    def __init__(self, db: Session, settings: Settings, ntfy: NtfyClient | None = None) -> None:
        self.db = db
        self.settings = settings
        self.ntfy = ntfy or NtfyClient(settings)

    def notify_if_eligible(self, project: Project) -> bool:
        analysis = project.analysis
        if not analysis or project.notified or analysis.score < self.settings.notify_score_threshold:
            return False
        if not self.settings.ntfy_topic:
            return False
        data = analysis.data
        message = "\n".join(
            [
                f"Budget: {project.budget_min}-{project.budget_max} {project.currency}",
                f"Score: {analysis.score}/100 ({analysis.recommendation})",
                f"Estimated time: {data.get('estimated_hours_min')}-{data.get('estimated_hours_max')} hours",
                f"Recommended bid: {analysis.recommended_bid_amount} {analysis.currency}",
                f"AI assistance: {data.get('ai_assistance_ratio')}%",
                "Risks: " + "; ".join(data.get("risks", [])[:3]),
                f"Review: {self.settings.app_base_url.rstrip('/')}/projects/{project.freelancer_project_id}",
                f"Freelancer: {project.project_url}",
            ]
        )
        record = Notification(project=project, channel="ntfy", status="pending", payload={"message": message})
        self.db.add(record)
        try:
            response = self.ntfy.publish(project.title[:80], message, tags=["briefcase"], click=project.project_url)
            record.status = "sent" if response.get("ok") else "skipped"
            record.error_message = response.get("message", "")
            if response.get("ok"):
                from app.models.entities import utcnow

                record.sent_at = utcnow()
                project.notified = True
                project.status = "notified"
                audit(self.db, "notification_sent", project.id, {"channel": "ntfy", "score": analysis.score})
                self.db.commit()
                return True
        except Exception as exc:
            record.status = "failed"
            record.error_message = str(exc)
            audit(self.db, "notification_failed", project.id, {"error": str(exc)})
        self.db.commit()
        return False
