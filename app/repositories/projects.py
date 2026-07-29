from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload

from app.models import Project
from app.schemas.project import NormalizedProject


class ProjectRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, freelancer_project_id: int, include_related: bool = True) -> Project | None:
        statement: Select[tuple[Project]] = select(Project).where(Project.freelancer_project_id == freelancer_project_id)
        if include_related:
            statement = statement.options(joinedload(Project.analysis), joinedload(Project.draft))
        return self.db.scalars(statement).unique().first()

    def list(self, status: str | None = None) -> list[Project]:
        statement: Select[tuple[Project]] = select(Project).options(joinedload(Project.analysis), joinedload(Project.draft))
        if status:
            statement = statement.where(Project.status == status)
        return list(self.db.scalars(statement.order_by(Project.updated_at.desc())).unique())

    def create_from_normalized(self, item: NormalizedProject) -> Project:
        project = Project(
            freelancer_project_id=item.freelancer_project_id,
            title=item.title,
            description=item.description,
            project_url=item.project_url,
            currency=item.currency,
            project_type=item.project_type,
            budget_min=item.budget_min,
            budget_max=item.budget_max,
            budget_usd_min=item.budget_usd_min,
            budget_usd_max=item.budget_usd_max,
            published_at=item.published_at,
            bid_count=item.bid_count,
            employer_id=item.employer_id,
            employer_rating=item.employer_rating,
            payment_verified=item.payment_verified,
            employer_history=item.employer_history,
            skills=item.skills,
            raw_data=item.raw_data,
        )
        self.db.add(project)
        return project

    def refresh_from_normalized(self, project: Project, item: NormalizedProject) -> Project:
        project.title = item.title
        project.description = item.description
        project.project_url = item.project_url
        project.currency = item.currency
        project.project_type = item.project_type
        project.budget_min = item.budget_min
        project.budget_max = item.budget_max
        project.budget_usd_min = item.budget_usd_min
        project.budget_usd_max = item.budget_usd_max
        project.published_at = item.published_at
        project.bid_count = item.bid_count
        project.employer_id = item.employer_id
        project.employer_rating = item.employer_rating
        project.payment_verified = item.payment_verified
        project.employer_history = item.employer_history
        project.skills = item.skills
        project.raw_data = item.raw_data
        return project

