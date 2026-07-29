from app.schemas.project import NormalizedProject
from app.services.config_service import FilterConfig
from app.services.filter_service import FilterService


def test_accepts_matching_project() -> None:
    service = FilterService(FilterConfig(include_keywords=["python"], exclude_keywords=["captcha"]))
    decision = service.evaluate(
        NormalizedProject(freelancer_project_id=1, title="Python API", project_type="fixed", budget_usd_max=500)
    )
    assert decision.accepted is True


def test_hard_exclusion_wins() -> None:
    service = FilterService(FilterConfig(include_keywords=["python"], exclude_keywords=["captcha"]))
    decision = service.evaluate(
        NormalizedProject(
            freelancer_project_id=1,
            title="Python captcha bypass",
            description="Bypass verification",
            project_type="fixed",
            budget_usd_max=500,
        )
    )
    assert decision.accepted is False
    assert "captcha" in decision.reason


def test_hard_deny_rejects_captcha_variants_even_without_yaml_rule() -> None:
    service = FilterService(FilterConfig(include_keywords=["automation"], exclude_keywords=[]))
    decision = service.evaluate(
        NormalizedProject(
            freelancer_project_id=2,
            title="Automate captcha bypass",
            description="Solve verification challenges",
            project_type="fixed",
            budget_usd_max=500,
        )
    )
    assert decision.accepted is False
    assert decision.reason.startswith("Hard-deny policy")
