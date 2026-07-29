import pytest

from app.models import Project
from app.services.analysis_service import AnalysisService
from app.services.bid_service import BidSafetyError, BidService
from app.services.project_service import ProjectService


def prepared_project(db, settings) -> Project:
    ProjectService(db, settings).fetch_projects()
    AnalysisService(db, settings).analyze_pending()
    return db.query(Project).filter(Project.status == "analyzed").one()


def test_approval_then_dry_run_is_allowed(db, settings) -> None:
    project = prepared_project(db, settings)
    service = BidService(db, settings)
    service.approve(project)
    record = service.submit(project, confirm=True, dry_run=True)
    assert record.status == "dry_run"
    assert project.status == "approved"


def test_real_submission_is_never_allowed_in_mock_mode(db, settings) -> None:
    project = prepared_project(db, settings)
    service = BidService(db, settings)
    service.approve(project)
    with pytest.raises(BidSafetyError, match="Mock mode"):
        service.submit(project, confirm=True, dry_run=False)


def test_second_confirmation_is_required(db, settings) -> None:
    project = prepared_project(db, settings)
    service = BidService(db, settings)
    service.approve(project)
    with pytest.raises(BidSafetyError, match="second explicit confirmation"):
        service.submit(project, confirm=False, dry_run=True)


def test_filtered_project_cannot_be_approved(db, settings) -> None:
    ProjectService(db, settings).fetch_projects()
    project = db.query(Project).filter(Project.status == "filtered_out").first()
    assert project is not None
    with pytest.raises(BidSafetyError, match="cannot be approved"):
        BidService(db, settings).approve(project)
