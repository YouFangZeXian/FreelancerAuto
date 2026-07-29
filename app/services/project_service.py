from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients.freelancer import FreelancerClient, normalize_project
from app.core.config import Settings
from app.models import FilterRuleSnapshot, Project, RuntimeSetting
from app.repositories.projects import ProjectRepository
from app.services.audit_service import audit
from app.services.config_service import load_filters
from app.services.filter_service import FilterService
from app.services.strategy_service import apply_strategy_filter_keywords


class ProjectService:
    FETCH_CURSOR_KEY = "active_projects_scan_offset"

    def __init__(self, db: Session, settings: Settings, freelancer: FreelancerClient | None = None) -> None:
        self.db = db
        self.settings = settings
        self.freelancer = freelancer or FreelancerClient(settings)
        self.repository = ProjectRepository(db)

    def fetch_projects(self, query: str = "") -> dict[str, int]:
        rules = apply_strategy_filter_keywords(load_filters(self.settings.filters_path), self.settings.operating_mode)
        snapshot = FilterRuleSnapshot(version=self._next_rule_version(), rules=rules.model_dump(), is_active=True)
        self.db.add(snapshot)
        filter_service = FilterService(rules)
        scan_offset = self._load_scan_offset()
        fetched = self.freelancer.search_active_projects(
            query=query,
            project_types=rules.allowed_project_types,
            limit=self.settings.freelancer_fetch_limit,
            offset=scan_offset,
        )
        next_offset = 0 if len(fetched) < self.settings.freelancer_fetch_limit else scan_offset + len(fetched)
        self._save_scan_offset(next_offset)
        known_ids = set(self.db.scalars(select(Project.freelancer_project_id)))
        result = {
            "fetched": len(fetched), "new": 0, "updated": 0, "known_skipped": 0,
            "pending_analysis": 0, "filtered_out": 0, "scan_offset": scan_offset, "next_offset": next_offset,
        }
        for raw in fetched:
            if int(raw["id"]) in known_ids:
                result["known_skipped"] += 1
                continue
            normalized = normalize_project(raw, self.settings.freelancer_base_url)
            project = self.repository.create_from_normalized(normalized)
            self.db.flush()
            result["new"] += 1
            decision = filter_service.evaluate(normalized)
            if not decision.accepted and decision.reason.startswith("Hard-deny policy"):
                project.filter_reason = decision.reason
                project.status = "filtered_out"
                result["filtered_out"] += 1
                audit(self.db, "project_hard_denied", project.id, {"reason": decision.reason})
                continue
            project.filter_reason = decision.reason
            project.status = "pending_analysis" if decision.accepted else "filtered_out"
            result["pending_analysis" if decision.accepted else "filtered_out"] += 1
            audit(
                self.db,
                "project_discovered",
                project.id,
                {"freelancer_project_id": project.freelancer_project_id, "filter_result": decision.reason},
            )
        self.db.commit()
        return result

    def get_detail(self, freelancer_project_id: int) -> Project | None:
        return self.repository.get(freelancer_project_id)

    def _next_rule_version(self) -> int:
        latest = self.db.query(FilterRuleSnapshot).order_by(FilterRuleSnapshot.version.desc()).first()
        return (latest.version if latest else 0) + 1

    def _load_scan_offset(self) -> int:
        row = self.db.query(RuntimeSetting).filter(RuntimeSetting.key == self.FETCH_CURSOR_KEY).first()
        try:
            return max(int(row.value), 0) if row else 0
        except ValueError:
            return 0

    def _save_scan_offset(self, offset: int) -> None:
        row = self.db.query(RuntimeSetting).filter(RuntimeSetting.key == self.FETCH_CURSOR_KEY).first()
        if row is None:
            self.db.add(RuntimeSetting(key=self.FETCH_CURSOR_KEY, value=str(offset)))
        else:
            row.value = str(offset)
