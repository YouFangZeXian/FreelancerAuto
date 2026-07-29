from datetime import datetime, timezone
from types import SimpleNamespace

from app.schemas.analysis import AnalysisResult
from app.services.analysis_service import build_system_prompt
from app.services.config_service import FilterConfig
from app.services.strategy_service import (
    apply_strategy_filter_keywords,
    apply_strategy_scoring,
    normalize_strategy_mode,
    starter_progress,
)


def _result(*, recommendation: str = "bid", starter_score: float = 7.5) -> AnalysisResult:
    return AnalysisResult(
        score=78,
        recommendation=recommendation,
        summary_zh="测试",
        requirements=[],
        skill_match=[],
        skill_gaps=[],
        estimated_hours_min=2,
        estimated_hours_max=5,
        recommended_bid_amount=35,
        currency="USD",
        recommended_delivery_days=1,
        effective_hourly_rate=7,
        ai_assistance_ratio=60,
        confidence=80,
        delivery_clarity=8,
        client_reliability=8,
        change_risk=2,
        five_star_probability=8,
        portfolio_fit=7,
        starter_score=starter_score,
        risks=[],
        red_flags=[],
        questions_for_client=[],
        execution_plan=["测试"],
        proposal_en="Hello" if recommendation != "skip" else "",
        reasoning_summary_zh="测试",
    )


def _project(**updates):
    values = {
        "title": "Quick small Python fix",
        "description": "Need today. This is a clear one page small bug fix with explicit delivery requirements.",
        "budget_usd_max": 50,
        "budget_usd_min": 30,
        "budget_max": 50,
        "budget_min": 30,
        "project_type": "fixed",
        "bid_count": 8,
        "payment_verified": True,
        "published_at": datetime.now(timezone.utc),
        "raw_data": {"attachments": [{"id": 1}]},
    }
    values.update(updates)
    return SimpleNamespace(**values)


def test_starter_mode_adds_explainable_review_signals() -> None:
    result, details = apply_strategy_scoring(_project(), _result(), "starter")

    assert result.starter_score > 7.5
    assert details["mode"] == "starter"
    assert "固定价格项目" in details["local_signals"]
    assert details["starter_score"] <= 10


def test_starter_mode_never_overrides_skip() -> None:
    result, details = apply_strategy_scoring(_project(), _result(recommendation="skip", starter_score=9.5), "starter")

    assert result.recommendation == "skip"
    assert result.starter_score == 0
    assert details["starter_score"] == 0


def test_mode_prompts_and_progress_are_available() -> None:
    assert normalize_strategy_mode("unknown") == "starter"
    assert "five-star review" in build_system_prompt("starter")
    assert "High Value" in build_system_prompt("high_value")
    assert starter_progress(5, 0)["should_suggest_normal_mode"] is True


def test_starter_mode_adds_entry_keywords_without_changing_existing_rules() -> None:
    rules = FilterConfig(include_keywords=["python"], exclude_keywords=["captcha"])
    starter_rules = apply_strategy_filter_keywords(rules, "starter")

    assert "python" in starter_rules.include_keywords
    assert "background removal" in starter_rules.include_keywords
    assert starter_rules.exclude_keywords == ["captcha"]
    assert apply_strategy_filter_keywords(rules, "normal") == rules
