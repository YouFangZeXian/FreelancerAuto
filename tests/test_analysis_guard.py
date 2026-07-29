from app.schemas.analysis import AnalysisResult
from app.services.analysis_guard import prevent_unsupported_skill_mismatch_skip


def _result(**changes) -> AnalysisResult:
    data = {
        "score": 20,
        "recommendation": "skip",
        "summary_zh": "项目需求与自由职业者技能不匹配，缺乏必需的PHP和CMS经验。",
        "requirements": [],
        "skill_match": [],
        "skill_gaps": ["PHP", "CMS"],
        "estimated_hours_min": 10,
        "estimated_hours_max": 20,
        "recommended_bid_amount": 1000,
        "currency": "USD",
        "recommended_delivery_days": 7,
        "effective_hourly_rate": 50,
        "ai_assistance_ratio": 50,
        "confidence": 60,
        "risks": [],
        "red_flags": [],
        "questions_for_client": [],
        "execution_plan": [],
        "proposal_en": "",
        "reasoning_summary_zh": "PHP 和 CMS 只是客户给出的可选实现方案。",
    }
    return AnalysisResult.model_validate(data | changes)


def test_vague_skill_mismatch_skip_becomes_manual_review() -> None:
    adjusted, details = prevent_unsupported_skill_mismatch_skip(_result())

    assert adjusted.recommendation == "review"
    assert details["applied"] is True
    assert "人工复核" in adjusted.summary_zh


def test_explicit_hard_requirement_with_evidence_remains_skip() -> None:
    adjusted, details = prevent_unsupported_skill_mismatch_skip(
        _result(
            hard_skill_mismatch=True,
            skill_mismatch_evidence=["Must hold an active government security clearance."],
            summary_zh="必须持有政府安全许可。",
        )
    )

    assert adjusted.recommendation == "skip"
    assert details["applied"] is False
