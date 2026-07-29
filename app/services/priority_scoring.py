from __future__ import annotations

import re
from typing import Any

from app.models import Project
from app.schemas.analysis import AnalysisResult
from app.services.config_service import FilterConfig


def apply_priority_score(
    project: Project, result: AnalysisResult, rules: FilterConfig
) -> tuple[AnalysisResult, dict[str, Any]]:
    """Raise eligible, high-value projects to the configured score floor without bypassing AI safety decisions."""
    matched_keywords = _matched_keywords(project, rules.priority_keywords)
    score_before = result.score
    eligible = bool(matched_keywords) and result.recommendation != "skip"
    score_after = max(score_before, rules.priority_score_floor) if eligible else score_before
    adjustment = {
        "matched_keywords": matched_keywords,
        "score_floor": rules.priority_score_floor,
        "score_before": score_before,
        "score_after": score_after,
        "applied": eligible and score_after != score_before,
        "not_applied_reason": "AI 建议跳过，未覆盖安全判断" if matched_keywords and not eligible else "",
    }
    return result.model_copy(update={"score": score_after}), adjustment


def _matched_keywords(project: Project, keywords: list[str]) -> list[str]:
    text = " ".join([project.title, project.description, *project.skills]).lower()
    return [keyword for keyword in keywords if _matches_keyword(text, keyword)]


def _matches_keyword(text: str, keyword: str) -> bool:
    """Match whole English words/phrases so short terms such as `ai` do not match `email` or `paid`."""
    normalized = keyword.strip().lower()
    if not normalized:
        return False
    expression = re.escape(normalized).replace(r"\ ", r"\s+")
    return bool(re.search(rf"(?<![a-z0-9]){expression}(?![a-z0-9])", text))
