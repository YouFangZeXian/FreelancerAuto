from __future__ import annotations

import re
from typing import Any

from app.schemas.analysis import AnalysisResult


_VAGUE_SKILL_MISMATCH = re.compile(
    r"skill mismatch|skills? (?:do not|does not|don't|doesn't|are not) match|"
    r"lack(?:s|ing)? (?:required|necessary) (?:skills?|experience)|"
    r"技能不匹配|缺乏(?:必需|必要).{0,25}|没有相关标签",
    flags=re.IGNORECASE,
)


def prevent_unsupported_skill_mismatch_skip(result: AnalysisResult) -> tuple[AnalysisResult, dict[str, Any]]:
    """Downgrade an unsupported skill-mismatch skip to manual review instead of rejecting it outright."""
    narrative = " ".join([result.summary_zh, result.reasoning_summary_zh, *result.risks])
    vague_skill_skip = result.recommendation == "skip" and bool(_VAGUE_SKILL_MISMATCH.search(narrative))
    supported = result.hard_skill_mismatch and bool(result.skill_mismatch_evidence)
    details = {
        "applied": vague_skill_skip and not supported,
        "hard_skill_mismatch": result.hard_skill_mismatch,
        "skill_mismatch_evidence": result.skill_mismatch_evidence,
    }
    if not details["applied"]:
        return result, details

    summary = result.summary_zh.rstrip()
    clarification = "未找到描述中的明确硬性技术要求，已转为人工复核。"
    if clarification not in summary:
        summary = f"{summary} {clarification}".strip()
    return result.model_copy(update={"recommendation": "review", "summary_zh": summary}), details
