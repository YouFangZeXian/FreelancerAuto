from app.models import Project
from app.services.analysis_service import AnalysisService
from app.services.project_service import ProjectService


def test_fetch_dedupes_and_filters(db, settings) -> None:
    first = ProjectService(db, settings).fetch_projects()
    second = ProjectService(db, settings).fetch_projects()
    assert first["new"] == 3
    assert second["new"] == 0
    assert db.query(Project).count() == 3
    assert db.query(Project).filter(Project.status == "pending_analysis").count() == 1
    assert db.query(Project).filter(Project.status == "filtered_out").count() == 2


def test_dry_run_analysis_creates_valid_draft(db, settings) -> None:
    ProjectService(db, settings).fetch_projects()
    result = AnalysisService(db, settings).analyze_pending()
    project = db.query(Project).filter(Project.status == "analyzed").one()
    assert result == {"requested": 1, "analyzed": 1, "failed": 0}
    assert 0 <= project.analysis.score <= 100
    assert project.analysis.data["recommendation"] in {"bid", "review", "skip"}
    assert project.draft.proposal_en

