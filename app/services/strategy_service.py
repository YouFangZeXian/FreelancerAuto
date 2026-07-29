from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models import Project
from app.schemas.analysis import AnalysisResult
from app.services.config_service import FilterConfig


STARTER_MODE = "starter"
NORMAL_MODE = "normal"
HIGH_VALUE_MODE = "high_value"

OPERATING_MODES: dict[str, dict[str, str]] = {
    STARTER_MODE: {
        "label": "Starter（破零模式）",
        "short_label": "破零模式",
        "description": "优先小而明确、低风险、易交付的项目，目标是积累高质量五星评价和作品集。",
    },
    NORMAL_MODE: {
        "label": "Normal（正常模式）",
        "short_label": "正常模式",
        "description": "在项目匹配度、风险、报价和长期收益之间保持平衡。",
    },
    HIGH_VALUE_MODE: {
        "label": "High Value（高价值模式）",
        "short_label": "高价值模式",
        "description": "后期用于优先审查高预算、高技术价值和可持续合作机会的项目。",
    },
}

STARTER_INCLUDE_KEYWORDS = (
    "image edit", "photoshop", "remove object", "background removal", "retouch", "simple edit",
    "watermark removal", "photo editing", "pdf", "word", "excel", "formatting", "copy typing",
    "typing", "data entry", "data processing", "chinese", "simplified chinese", "translation chinese",
    "proofreading chinese", "chinese typing", "html", "css", "landing page", "fix css", "bug fix",
    "small website", "bootstrap", "small script", "python script", "automation", "api", "json", "csv",
    "selenium", "web scraping", "fix bug", "chatgpt", "prompt", "ai", "openai", "claude", "gemini",
)


def normalize_strategy_mode(value: str | None) -> str:
    return value if value in OPERATING_MODES else STARTER_MODE


def get_strategy_meta(value: str | None) -> dict[str, str]:
    mode = normalize_strategy_mode(value)
    return {"id": mode, **OPERATING_MODES[mode]}


def apply_strategy_filter_keywords(rules: FilterConfig, mode_value: str | None) -> FilterConfig:
    """Add Starter entry keywords while preserving every user-managed filter and exclusion rule."""
    if normalize_strategy_mode(mode_value) != STARTER_MODE:
        return rules
    existing = {item.casefold() for item in rules.include_keywords}
    additions = [item for item in STARTER_INCLUDE_KEYWORDS if item.casefold() not in existing]
    return rules.model_copy(update={"include_keywords": [*rules.include_keywords, *additions]})


def starter_progress(review_count: int, completed_projects: int) -> dict[str, Any]:
    reviews = max(int(review_count), 0)
    completed = max(int(completed_projects), 0)
    should_suggest = reviews >= 5 or completed >= 10
    return {
        "reviews": reviews,
        "completed_projects": completed,
        "review_target": 5,
        "completed_target": 10,
        "should_suggest_normal_mode": should_suggest,
        "message": (
            "已达到破零阶段目标，建议切换到 Normal（正常模式），开始更重视利润和长期价值。"
            if should_suggest
            else "这是手动记录的破零进度；达到 5 个五星评价或 10 个完成项目时，系统会提示切换 Normal。"
        ),
    }


def apply_strategy_scoring(
    project: Project, result: AnalysisResult, mode_value: str | None
) -> tuple[AnalysisResult, dict[str, Any]]:
    """Add explainable mode metadata without overriding a safety-oriented AI skip decision."""
    mode = normalize_strategy_mode(mode_value)
    if mode != STARTER_MODE:
        return result, {
            "mode": mode,
            "starter_score": round(result.starter_score, 1),
            "local_signals": [],
            "mode_recommendation": (
                "优先关注高预算、技术壁垒和长期合作价值。"
                if mode == HIGH_VALUE_MODE
                else "按综合匹配度、风险和合理收益进行平衡推荐。"
            ),
        }

    if result.recommendation == "skip":
        return result.model_copy(update={"starter_score": 0}), {
            "mode": mode,
            "starter_score": 0.0,
            "model_starter_score": round(result.starter_score, 1),
            "local_signals": ["AI 安全判断为跳过，破零偏好不会覆盖该判断"],
            "mode_recommendation": "不推荐作为破零项目。",
        }

    signals: list[str] = []
    adjustment = 0.0
    budget = project.budget_usd_max or project.budget_usd_min or project.budget_max or project.budget_min or 0.0
    if 15 <= budget <= 80:
        adjustment += 0.5
        signals.append("预算处于破零优先区间（15–80 USD）")
    elif budget > 80:
        adjustment += 0.1
        signals.append("预算高于破零优先区间，仍可人工评估")

    if project.project_type == "fixed":
        adjustment += 0.4
        signals.append("固定价格项目")
    if result.estimated_hours_max <= 6:
        adjustment += 0.6
        signals.append("预计可在 6 小时内完成")
    elif result.estimated_hours_max <= 12:
        adjustment += 0.2
        signals.append("预计工作量较小")
    if project.bid_count < 20:
        adjustment += 0.45
        signals.append("当前投标数少于 20")
    if project.payment_verified:
        adjustment += 0.35
        signals.append("雇主付款已验证")
    if len((project.description or "").strip()) >= 220:
        adjustment += 0.25
        signals.append("项目描述较完整")
    if _has_attachments(project.raw_data):
        adjustment += 0.2
        signals.append("项目附有附件")
    if _is_recent(project):
        adjustment += 0.45
        signals.append("项目发布不足 6 小时")
    if _has_quick_task_signal(project):
        adjustment += 0.35
        signals.append("命中快速、小型交付信号")

    dimension_score = (
        result.delivery_clarity * 0.25
        + result.client_reliability * 0.20
        + (10 - result.change_risk) * 0.15
        + result.five_star_probability * 0.30
        + result.portfolio_fit * 0.10
    )
    base_score = result.starter_score if result.starter_score > 0 else dimension_score
    starter_score = round(min(10.0, base_score + adjustment), 1)
    updated = result.model_copy(update={"starter_score": starter_score})
    recommendation = (
        "强烈推荐用于破零：交付与五星评价潜力都较好。"
        if starter_score >= 8.5
        else "适合进入破零人工确认队列。"
        if starter_score >= 6.5
        else "可保留，但不应优先于更清晰、更低风险的破零项目。"
    )
    return updated, {
        "mode": mode,
        "starter_score": starter_score,
        "model_starter_score": round(result.starter_score, 1),
        "local_signals": signals,
        "mode_recommendation": recommendation,
    }


def stored_starter_score(project: Project) -> float:
    if not project.analysis:
        return -1.0
    strategy = project.analysis.data.get("strategy", {}) if project.analysis.data else {}
    value = strategy.get("starter_score", project.analysis.data.get("starter_score", 0))
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _has_attachments(raw_data: dict[str, Any] | None) -> bool:
    if not raw_data:
        return False
    for key in ("attachments", "files", "file_count"):
        value = raw_data.get(key)
        if isinstance(value, (list, dict)) and value:
            return True
        if isinstance(value, int) and value > 0:
            return True
    return False


def _is_recent(project: Project) -> bool:
    if not project.published_at:
        return False
    published_at = project.published_at
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    age_seconds = (datetime.now(timezone.utc) - published_at).total_seconds()
    return 0 <= age_seconds < 6 * 60 * 60


def _has_quick_task_signal(project: Project) -> bool:
    text = f"{project.title} {project.description}".lower()
    terms = (
        "need today", "quick task", "simple fix", "minor change", "urgent", "easy work",
        "small project", "few images", "fix only", "one page", "one issue", "small bug",
    )
    return any(term in text for term in terms)
