from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients.freelancer import FreelancerAPIError, FreelancerClient, normalize_project
from app.core.config import Settings
from app.models import BidSubmission, Project
from app.services.audit_service import audit


class BidSafetyError(RuntimeError):
    pass


class BidService:
    def __init__(self, db: Session, settings: Settings, freelancer: FreelancerClient | None = None) -> None:
        self.db = db
        self.settings = settings
        self.freelancer = freelancer or FreelancerClient(settings)

    def approve(self, project: Project, actor: str = "user") -> None:
        if project.status == "filtered_out":
            raise BidSafetyError("A locally filtered or hard-denied project cannot be approved")
        if project.analysis and (project.analysis.recommendation == "skip" or project.analysis.data.get("red_flags")):
            raise BidSafetyError("A project with a skip recommendation or red flags cannot be approved")
        if not project.draft or not project.draft.proposal_en.strip():
            raise BidSafetyError("A non-empty proposal draft is required before approval")
        if project.status in {"submitted", "submission_failed"}:
            raise BidSafetyError("This project cannot be approved after a submission attempt")
        from app.models.entities import utcnow

        project.draft.approved_at = utcnow()
        project.draft.rejected_at = None
        project.reviewed = True
        project.status = "approved"
        audit(self.db, "bid_approved", project.id, actor=actor)
        self.db.commit()

    def reject(self, project: Project, reason: str = "", actor: str = "user") -> None:
        if not project.draft:
            raise BidSafetyError("No draft exists to reject")
        from app.models.entities import utcnow

        project.draft.rejected_at = utcnow()
        project.draft.approval_note = reason
        project.reviewed = True
        project.status = "rejected"
        audit(self.db, "bid_rejected", project.id, {"reason": reason}, actor)
        self.db.commit()

    def mark_manual(self, project: Project, actor: str = "user") -> None:
        if project.status == "filtered_out" or (project.analysis and project.analysis.data.get("red_flags")):
            raise BidSafetyError("A locally filtered or hard-denied project cannot be marked for manual bidding")
        project.reviewed = True
        project.status = "manual_submission_required"
        audit(self.db, "manual_submission_required", project.id, actor=actor)
        self.db.commit()

    def submit(self, project: Project, confirm: bool, dry_run: bool = False, actor: str = "user") -> BidSubmission:
        self._preflight(project, confirm=confirm, dry_run=dry_run)
        draft = project.draft
        assert draft is not None
        requester = self.freelancer.get_self()
        bidder_id = self.settings.freelancer_bidder_id or int(requester["id"])
        request_payload = {
            "project_id": project.freelancer_project_id,
            "bidder_id": bidder_id,
            "amount": draft.bid_amount,
            "period": draft.delivery_days,
            "description": draft.proposal_en,
        }
        if dry_run:
            record = BidSubmission(project=project, status="dry_run", request_payload=request_payload, is_dry_run=True)
            self.db.add(record)
            audit(self.db, "bid_dry_run", project.id, {"amount": draft.bid_amount}, actor)
            self.db.commit()
            return record
        record = BidSubmission(project=project, status="pending", request_payload=request_payload, is_dry_run=False)
        self.db.add(record)
        self.db.commit()
        try:
            response = self.freelancer.submit_bid(
                project.freelancer_project_id,
                bidder_id,
                draft.bid_amount,
                draft.delivery_days,
                draft.proposal_en,
            )
        except FreelancerAPIError as exc:
            record.status = "failed"
            record.error_message = str(exc)
            project.status = "submission_failed"
            audit(self.db, "bid_submission_failed", project.id, {"error": str(exc)}, actor)
            self.db.commit()
            raise BidSafetyError(str(exc)) from exc
        record.status = "submitted"
        record.response_payload = response
        record.external_bid_id = response.get("id")
        project.status = "submitted"
        audit(self.db, "bid_submitted", project.id, {"external_bid_id": record.external_bid_id}, actor)
        self.db.commit()
        return record

    def _preflight(self, project: Project, confirm: bool, dry_run: bool) -> None:
        if not project.draft:
            raise BidSafetyError("No bid draft exists")
        if not project.draft.approved_at:
            raise BidSafetyError("The draft must be approved in the dashboard before submission")
        if not confirm:
            raise BidSafetyError("A second explicit confirmation is required")
        if not project.draft.proposal_en.strip():
            raise BidSafetyError("Proposal cannot be empty")
        if project.status != "approved":
            raise BidSafetyError(f"Project is not in approved status: {project.status}")
        existing = self.db.scalars(
            select(BidSubmission).where(BidSubmission.project_id == project.id, BidSubmission.status == "submitted")
        ).first()
        if existing:
            raise BidSafetyError("A bid was already submitted for this project")
        if dry_run:
            return
        if self.settings.freelancer_mock_mode:
            raise BidSafetyError("Mock mode never permits real submission; use --dry-run or configure the live API")
        if not self.settings.freelancer_bid_submission_enabled:
            raise BidSafetyError("Real submission is disabled. Set FREELANCER_BID_SUBMISSION_ENABLED=true only after review")
        if not self.settings.freelancer_access_token:
            raise BidSafetyError("FREELANCER_ACCESS_TOKEN is not configured")
        current = self.freelancer.get_project(project.freelancer_project_id)
        normalized = normalize_project(current, self.settings.freelancer_base_url)
        status = str(current.get("frontend_project_status") or current.get("status") or "").lower()
        if status not in {"open", "active"}:
            raise BidSafetyError(f"Project is no longer open for bidding: {status or 'unknown'}")
        self._validate_amount(project, normalized)
        self._validate_rate_limits()

    def _validate_amount(self, project: Project, current: Any) -> None:
        draft = project.draft
        assert draft is not None
        if current.budget_min is not None and draft.bid_amount < current.budget_min:
            raise BidSafetyError("Bid amount is below the current project minimum")
        if current.budget_max is not None and draft.bid_amount > current.budget_max:
            raise BidSafetyError("Bid amount is above the current project maximum")

    def _validate_rate_limits(self) -> None:
        now = datetime.now(timezone.utc)
        hour_start = now - timedelta(hours=1)
        day_start = now - timedelta(days=1)
        hourly = self.db.query(BidSubmission).filter(
            BidSubmission.status == "submitted", BidSubmission.created_at >= hour_start
        ).count()
        daily = self.db.query(BidSubmission).filter(
            BidSubmission.status == "submitted", BidSubmission.created_at >= day_start
        ).count()
        if hourly >= self.settings.max_bids_per_hour:
            raise BidSafetyError("Hourly bid submission limit has been reached")
        if daily >= self.settings.max_bids_per_day:
            raise BidSafetyError("Daily bid submission limit has been reached")
