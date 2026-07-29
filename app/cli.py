from __future__ import annotations

import argparse
import json
import sys
import time

import uvicorn

from app.ai.provider import OpenAICompatibleProvider
from app.clients.freelancer import FreelancerClient
from app.clients.ntfy import NtfyClient
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal, init_db
from app.models import Project
from app.repositories.projects import ProjectRepository
from app.services.analysis_service import AnalysisService
from app.services.bid_service import BidSafetyError, BidService
from app.services.config_service import load_filters, load_profile
from app.services.cycle_service import CycleService
from app.services.project_service import ProjectService
from app.services.runtime_settings import effective_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="FreelancerAuto command line interface")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ["init-db", "check-config", "test-ai", "test-freelancer", "test-ntfy", "fetch-projects", "analyze-pending", "run-cycle", "list-projects", "serve", "worker"]:
        sub.add_parser(name)
    show = sub.add_parser("show-project")
    show.add_argument("project_id", type=int)
    draft = sub.add_parser("draft")
    draft.add_argument("project_id", type=int)
    approve = sub.add_parser("approve")
    approve.add_argument("project_id", type=int)
    bid = sub.add_parser("bid")
    bid.add_argument("project_id", type=int)
    mode = bid.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--confirm", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    args = build_parser().parse_args(argv)
    if args.command == "init-db":
        init_db()
        print("Database initialized")
        return 0
    init_db()
    with SessionLocal() as db:
        effective = effective_settings(db, settings)
        try:
            if args.command == "check-config":
                result = {
                    "filters": load_filters(effective.filters_path).model_dump(),
                    "profile": load_profile(effective.profile_path).model_dump(),
                    "freelancer_mode": "mock" if effective.freelancer_mock_mode else "live",
                    "ai_mode": "dry-run" if effective.ai_dry_run else "live",
                    "ntfy_configured": bool(effective.ntfy_topic),
                    "real_bid_submission_enabled": effective.freelancer_bid_submission_enabled,
                }
            elif args.command == "test-ai":
                result = OpenAICompatibleProvider(effective).test_connection()
            elif args.command == "test-freelancer":
                result = FreelancerClient(effective).test_connection()
            elif args.command == "test-ntfy":
                result = NtfyClient(effective).test_connection()
            elif args.command == "fetch-projects":
                fetch = ProjectService(db, effective).fetch_projects()
                analysis = AnalysisService(db, effective).analyze_pending(limit=effective.analysis_batch_limit)
                result = {"fetch": fetch, "analysis": analysis}
            elif args.command == "analyze-pending":
                result = AnalysisService(db, effective).analyze_pending()
            elif args.command == "run-cycle":
                result = CycleService(db, effective).run()
            elif args.command == "list-projects":
                result = [
                    {"id": item.freelancer_project_id, "status": item.status, "score": item.analysis.score if item.analysis else None, "title": item.title}
                    for item in ProjectRepository(db).list()
                ]
            elif args.command == "show-project":
                result = serialize_project(_get_project(db, args.project_id))
            elif args.command == "draft":
                project = _get_project(db, args.project_id)
                if not project.draft:
                    AnalysisService(db, effective).analyze_project(project)
                    db.refresh(project)
                result = serialize_project(project)
            elif args.command == "approve":
                project = _get_project(db, args.project_id)
                BidService(db, effective).approve(project, actor="cli-user")
                result = {"ok": True, "status": project.status, "message": "Approved; use bid --confirm for the second confirmation"}
            elif args.command == "bid":
                project = _get_project(db, args.project_id)
                record = BidService(db, effective).submit(project, confirm=True, dry_run=args.dry_run, actor="cli-user")
                result = {"id": record.id, "status": record.status, "dry_run": record.is_dry_run}
            elif args.command == "serve":
                uvicorn.run("app.main:app", host=effective.app_host, port=effective.app_port, reload=False)
                return 0
            elif args.command == "worker":
                from app.tasks.scheduler import build_scheduler

                scheduler = build_scheduler(effective)
                scheduler.start()
                print(f"Worker running every {effective.scheduler_interval_minutes} minutes. Press Ctrl+C to stop.")
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    scheduler.shutdown(wait=False)
                return 0
            else:
                raise RuntimeError(f"Unknown command: {args.command}")
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            return 0
        except (BidSafetyError, RuntimeError, ValueError, FileNotFoundError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1


def _get_project(db, project_id: int) -> Project:
    project = ProjectRepository(db).get(project_id)
    if not project:
        raise RuntimeError(f"Project {project_id} was not found")
    return project


def serialize_project(project: Project) -> dict[str, object]:
    return {
        "project_id": project.freelancer_project_id,
        "title": project.title,
        "status": project.status,
        "filter_reason": project.filter_reason,
        "budget": {"minimum": project.budget_min, "maximum": project.budget_max, "currency": project.currency},
        "skills": project.skills,
        "analysis": project.analysis.data if project.analysis else None,
        "draft": {
            "proposal_en": project.draft.proposal_en,
            "bid_amount": project.draft.bid_amount,
            "delivery_days": project.draft.delivery_days,
            "approved_at": project.draft.approved_at,
        } if project.draft else None,
        "url": project.project_url,
    }


if __name__ == "__main__":
    raise SystemExit(main())
