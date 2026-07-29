import json

import httpx

from app.ai.provider import OpenAICompatibleProvider
from app.schemas.analysis import AnalysisResult


def valid_result() -> dict:
    return {
        "score": 80,
        "recommendation": "bid",
        "summary_zh": "匹配",
        "requirements": ["API"],
        "skill_match": ["Python"],
        "skill_gaps": [],
        "estimated_hours_min": 5,
        "estimated_hours_max": 10,
        "recommended_bid_amount": 300,
        "currency": "USD",
        "recommended_delivery_days": 3,
        "effective_hourly_rate": 30,
        "ai_assistance_ratio": 60,
        "confidence": 85,
        "risks": [],
        "red_flags": [],
        "questions_for_client": [],
        "execution_plan": ["Build"],
        "proposal_en": "Hello, I can help with this API project.",
        "proposal_zh": "您好，我可以协助完成这个 API 项目。",
        "reasoning_summary_zh": "技能匹配。",
    }


def test_contract_rejects_extra_fields() -> None:
    data = valid_result() | {"unexpected": True}
    try:
        AnalysisResult.model_validate(data)
    except Exception:
        pass
    else:
        raise AssertionError("extra fields must be rejected")


def test_live_provider_parses_json(settings) -> None:
    settings = settings.model_copy(update={"ai_dry_run": False, "ai_base_url": "https://ai.example/v1", "ai_api_key": "secret", "ai_model": "test"})

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://ai.example/v1/chat/completions"
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(valid_result())}}]})

    provider = OpenAICompatibleProvider(settings, httpx.Client(transport=httpx.MockTransport(handler)))
    fallback = AnalysisResult.model_validate(valid_result())
    result, raw = provider.analyze("system", "user", fallback)
    assert result.score == 80
    assert raw["mode"] == "live"


def test_live_provider_normalizes_deepseek_fractional_percentages(settings) -> None:
    settings = settings.model_copy(update={"ai_dry_run": False, "ai_base_url": "https://ai.example/v1", "ai_api_key": "secret", "ai_model": "test"})
    response = valid_result() | {"ai_assistance_ratio": 0.7, "confidence": 0.3, "recommended_delivery_days": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(response)}}]})

    provider = OpenAICompatibleProvider(settings, httpx.Client(transport=httpx.MockTransport(handler)))
    fallback = AnalysisResult.model_validate(valid_result())
    result, raw = provider.analyze("system", "user", fallback)

    assert result.ai_assistance_ratio == 70
    assert result.confidence == 30
    assert result.recommended_delivery_days == fallback.recommended_delivery_days
    assert raw["normalizations"]["recommended_delivery_days"]["reason"] == "invalid_delivery_days_fallback"
