from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import create_app
from app.models import Project
from app.services.analysis_service import AnalysisService
from app.services.project_service import ProjectService
from app.services.runtime_settings import get_runtime_settings


def test_dashboard_and_project_detail(db, settings, monkeypatch) -> None:
    ProjectService(db, settings).fetch_projects()
    AnalysisService(db, settings).analyze_pending()
    app = create_app()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    response = client.get("/projects")
    assert response.status_code == 200
    assert "项目队列" in response.text
    assert "监控与审核" in response.text
    assert "建议投标" in response.text
    assert "Build a FastAPI automation dashboard" in response.text
    empty_numeric_filters = client.get("/projects?min_score=&budget_min=")
    assert empty_numeric_filters.status_code == 200
    assert "项目队列" in empty_numeric_filters.text
    detail = client.get("/projects/1000001")
    assert detail.status_code == 200
    assert "投标函与报价" in detail.text
    assert "英文 Proposal" in detail.text
    assert "中文译文（仅供核对，不会提交给客户）" in detail.text
    assert "Need a small Python FastAPI admin dashboard" in detail.text


def test_analyzed_projects_are_sorted_by_score_descending(db, settings) -> None:
    ProjectService(db, settings).fetch_projects()
    service = AnalysisService(db, settings)
    projects = db.query(Project).order_by(Project.freelancer_project_id).all()
    for project in projects[:2]:
        service.analyze_project(project)
    app = create_app()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    response = TestClient(app).get("/projects?status=analyzed")

    assert response.status_code == 200
    assert response.text.index("Build a FastAPI automation dashboard") < response.text.index("Academic cheating service request")


def test_starter_strategy_is_saved_and_sorts_analyzed_projects(db, settings) -> None:
    ProjectService(db, settings).fetch_projects()
    service = AnalysisService(db, settings)
    projects = db.query(Project).order_by(Project.freelancer_project_id).all()
    for project in projects[:2]:
        service.analyze_project(project)

    first, second = projects[:2]
    first_data = dict(first.analysis.data)
    first_data["strategy"] = {"starter_score": 2.0}
    first.analysis.data = first_data
    second_data = dict(second.analysis.data)
    second_data["strategy"] = {"starter_score": 9.4}
    second.analysis.data = second_data
    db.commit()

    app = create_app()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    saved = client.post(
        "/settings/strategy",
        data={"operating_mode": "starter", "starter_review_count": 3, "starter_completed_projects": 4},
    )
    assert saved.status_code == 200
    runtime = get_runtime_settings(db)
    assert runtime["operating_mode"] == "starter"
    assert runtime["starter_review_count"] == "3"

    response = client.get("/projects?status=analyzed")
    assert response.status_code == 200
    assert "Starter" in response.text
    assert response.text.index(second.title) < response.text.index(first.title)
