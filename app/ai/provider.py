from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from app.core.config import Settings
from app.schemas.analysis import AnalysisResult

logger = logging.getLogger(__name__)


class AIProviderError(RuntimeError):
    pass


class OpenAICompatibleProvider:
    """Small provider adapter for OpenAI-compatible chat-completions APIs."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._client = client or httpx.Client(timeout=float(settings.ai_timeout_seconds))

    def test_connection(self) -> dict[str, Any]:
        if self.settings.ai_dry_run:
            return {"ok": True, "mode": "dry-run", "message": "AI_DRY_RUN is enabled"}
        if not self.settings.is_ai_configured:
            return {"ok": False, "message": "AI_BASE_URL, AI_API_KEY, or AI_MODEL is missing"}
        result = self.complete_json(
            [
                {"role": "system", "content": "Return exactly a JSON object: {\"ok\": true}."},
                {"role": "user", "content": "connection test"},
            ]
        )
        return {"ok": result.get("ok") is True, "mode": "live", "response": result}

    def analyze(self, system_prompt: str, user_prompt: str, fallback: AnalysisResult) -> tuple[AnalysisResult, dict[str, Any]]:
        if self.settings.ai_dry_run:
            return fallback, {"mode": "dry-run", "message": "No external AI request was made"}
        raw = self.complete_json(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
        normalized, normalizations = _normalize_analysis_payload(raw, fallback)
        try:
            return AnalysisResult.model_validate(normalized), {
                "mode": "live",
                "response": raw,
                "normalizations": normalizations,
            }
        except Exception as exc:  # Pydantic error details are retained in the database, not exposed as a traceback.
            raise AIProviderError(f"AI response failed contract validation: {exc}") from exc

    def complete_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        endpoint = f"{self.settings.ai_base_url.rstrip('/')}/chat/completions"
        request = {
            "model": self.settings.ai_model,
            "messages": messages,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self.settings.ai_api_key}", "Content-Type": "application/json"}
        last_error: Exception | None = None
        for attempt in range(self.settings.ai_max_retries + 1):
            try:
                response = self._client.post(endpoint, json=request, headers=headers)
                if response.status_code in {408, 409, 429} or response.status_code >= 500:
                    raise AIProviderError(f"retryable AI HTTP {response.status_code}")
                response.raise_for_status()
                body = response.json()
                content = body["choices"][0]["message"]["content"]
                return _parse_json_object(content)
            except (httpx.HTTPError, KeyError, IndexError, ValueError, AIProviderError) as exc:
                last_error = exc
                if attempt >= self.settings.ai_max_retries:
                    break
                time.sleep(min(2**attempt, 8))
        raise AIProviderError(f"AI request failed after retries: {last_error}")


def _parse_json_object(content: str) -> dict[str, Any]:
    value = content.strip()
    if value.startswith("```"):
        value = value.split("\n", 1)[-1]
        if value.endswith("```"):
            value = value[:-3]
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("AI response is not a JSON object")
    return parsed


def _normalize_analysis_payload(payload: dict[str, Any], fallback: AnalysisResult) -> tuple[dict[str, Any], dict[str, Any]]:
    """Repair only unambiguous provider conventions before strict schema validation."""
    normalized = dict(payload)
    normalizations: dict[str, Any] = {}
    for field in ("ai_assistance_ratio", "confidence"):
        value = normalized.get(field)
        if isinstance(value, float) and 0 < value < 1:
            normalized_value = round(value * 100)
            normalized[field] = normalized_value
            normalizations[field] = {"from": value, "to": normalized_value, "reason": "fraction_to_percent"}

    delivery_days = normalized.get("recommended_delivery_days")
    if isinstance(delivery_days, (int, float)) and not isinstance(delivery_days, bool) and delivery_days < 1:
        normalized["recommended_delivery_days"] = fallback.recommended_delivery_days
        normalizations["recommended_delivery_days"] = {
            "from": delivery_days,
            "to": fallback.recommended_delivery_days,
            "reason": "invalid_delivery_days_fallback",
        }
    return normalized, normalizations
