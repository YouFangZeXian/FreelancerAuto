from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models import Project

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/projects")
def list_projects(
    status: str | None = Query(default=None),
    min_score: int | None = Query(default=None, ge=0, le=100),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    statement = select(Project).options(joinedload(Project.analysis)).order_by(Project.published_at.desc())
    if status:
        statement = statement.where(Project.status == status)
    projects = list(db.scalars(statement).unique())
    if min_score is not None:
        projects = [item for item in projects if item.analysis and item.analysis.score >= min_score]
    return [_serialize_project(project) for project in projects]


@router.get("/projects/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    project = db.scalars(
        select(Project)
        .where(Project.freelancer_project_id == project_id)
        .options(joinedload(Project.analysis), joinedload(Project.draft))
    ).unique().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    payload = _serialize_project(project)
    payload["description"] = project.description
    payload["analysis"] = project.analysis.data if project.analysis else None
    payload["draft"] = {
        "proposal_en": project.draft.proposal_en,
        "bid_amount": project.draft.bid_amount,
        "delivery_days": project.draft.delivery_days,
    } if project.draft else None
    return payload


def _serialize_project(project: Project) -> dict[str, object]:
    return {
        "project_id": project.freelancer_project_id,
        "title": project.title,
        "status": project.status,
        "project_type": project.project_type,
        "budget_min": project.budget_min,
        "budget_max": project.budget_max,
        "currency": project.currency,
        "bid_count": project.bid_count,
        "score": project.analysis.score if project.analysis else None,
        "recommendation": project.analysis.recommendation if project.analysis else None,
        "project_url": project.project_url,
    }

