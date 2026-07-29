from types import SimpleNamespace

from app.schemas.analysis import AnalysisResult
from app.services.config_service import FilterConfig
from app.services.priority_scoring import apply_priority_score


def _result(*, score: int, recommendation: str) -> AnalysisResult:
    return AnalysisResult(
        score=score,
        recommendation=recommendation,
        summary_zh="测试",
        requirements=[],
        skill_match=[],
        skill_gaps=[],
        estimated_hours_min=1,
        estimated_hours_max=2,
        recommended_bid_amount=10,
        currency="USD",
        recommended_delivery_days=1,
        effective_hourly_rate=10,
        ai_assistance_ratio=50,
        confidence=50,
        risks=[],
        red_flags=[],
        questions_for_client=[],
        execution_plan=[],
        proposal_en="Hello" if recommendation != "skip" else "",
        reasoning_summary_zh="测试",
    )


def _project(description: str) -> SimpleNamespace:
    return SimpleNamespace(title="Python dashboard", description=description, skills=["Python", "API"])


def test_priority_keyword_raises_eligible_project_to_score_floor() -> None:
    rules = FilterConfig(priority_keywords=["python", "api integration", "ai"], priority_score_floor=90)

    adjusted, details = apply_priority_score(
        _project("Need Python API integration with an AI assistant."), _result(score=72, recommendation="bid"), rules
    )

    assert adjusted.score == 90
    assert details["matched_keywords"] == ["python", "api integration", "ai"]
    assert details["applied"] is True


def test_short_priority_keyword_does_not_match_inside_another_word() -> None:
    rules = FilterConfig(priority_keywords=["ai"], priority_score_floor=90)

    adjusted, details = apply_priority_score(_project("Please connect our email service."), _result(score=72, recommendation="bid"), rules)

    assert adjusted.score == 72
    assert details["matched_keywords"] == []


def test_priority_keyword_does_not_override_ai_skip_recommendation() -> None:
    rules = FilterConfig(priority_keywords=["python"], priority_score_floor=90)

    adjusted, details = apply_priority_score(_project("Need Python work."), _result(score=5, recommendation="skip"), rules)

    assert adjusted.score == 5
    assert details["applied"] is False
    assert details["not_applied_reason"]
