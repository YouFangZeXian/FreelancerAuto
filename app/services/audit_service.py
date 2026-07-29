from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def audit(db: Session, event_type: str, project_id: int | None = None, details: dict[str, Any] | None = None, actor: str = "system") -> None:
    db.add(AuditLog(event_type=event_type, project_id=project_id, details=details or {}, actor=actor))

