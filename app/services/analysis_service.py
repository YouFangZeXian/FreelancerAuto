from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.provider import AIProviderError, OpenAICompatibleProvider
from app.core.config import Settings
from app.models import BidDraft, Project, ProjectAnalysis
from app.services.audit_service import audit
from app.services.analysis_guard import prevent_unsupported_skill_mismatch_skip
from app.services.config_service import ProfileConfig, load_filters, load_profile
from app.services.priority_scoring import apply_priority_score
from app.services.strategy_service import apply_strategy_scoring, normalize_strategy_mode


SYSTEM_PROMPT = """You are a careful project-fit analyst for a freelancer. Return ONLY a JSON object.
Use exactly this schema and every listed key:
{
  "score": 50,
  "recommendation": "bid|review|skip",
  "summary_zh": "",
  "description_zh": "",
  "hard_requirements": [],
  "preferred_options": [],
  "future_roadmap_items": [],
  "hard_skill_mismatch": false,
  "skill_mismatch_evidence": [],
  "alternative_stack_available": true,
  "learnable_skills": [],
  "requirements": [],
  "skill_match": [],
  "skill_gaps": [],
  "estimated_hours_min": 0,
  "estimated_hours_max": 0,
  "recommended_bid_amount": 0,
  "currency": "USD",
  "recommended_delivery_days": 1,
  "effective_hourly_rate": 0,
  "ai_assistance_ratio": 0,
  "confidence": 0,
  "delivery_clarity": 0,
  "client_reliability": 0,
  "change_risk": 0,
  "five_star_probability": 0,
  "portfolio_fit": 0,
  "starter_score": 0,
  "risks": [],
  "red_flags": [],
  "questions_for_client": [],
  "execution_plan": [],
  "proposal_en": "",
  "proposal_zh": "",
  "reasoning_summary_zh": ""
}
Numeric constraints: recommended_delivery_days must be an integer of at least 1. ai_assistance_ratio and confidence
must be integer percentages from 0 to 100: use 70 for 70%, never 0.7.
description_zh must be a faithful, complete Simplified Chinese translation of the supplied project description,
without adding requirements or advice. The currency field and effective_hourly_rate must use exactly the supplied
project budget currency.
Read the full description instead of treating Freelancer skill tags or the freelancer profile as hard requirements.
Classify each technology and feature as one of: hard_requirements (explicitly mandatory, must-have, or
non-negotiable), preferred_options (examples, recommendations, acceptable alternatives), or
future_roadmap_items (described as future, tomorrow, later, planned, eventually, or when integrated).
Future roadmap items are not part of the immediate delivery scope. Do not reject a project merely because it
mentions PHP, WordPress, CMS, React, Next.js, website design, or another optional implementation route.
Assess practical delivery using reasonable alternatives and AI-assisted implementation with Codex, documentation,
and established open-source libraries; a missing profile tag is not proof of inability to deliver standard work.
Set hard_skill_mismatch to true only when a critical technology or credential is explicitly mandatory, no reasonable
alternative is accepted, and it cannot reasonably be delivered. In that case skill_mismatch_evidence must quote or
identify the exact mandatory wording from the project description. Never use vague reasons such as "skills do not
match", "missing website/CMS experience", or "no relevant tag" to recommend skip. If a project is feasible but the
scope is uncertain, use recommendation "review" rather than "skip".
Never invent past experience or skills absent from the supplied profile. The English proposal must be tailored,
honest, ask clarifying questions where requirements are unclear, never claim to be an AI, and never promise
unverified delivery results. proposal_zh must be a faithful Simplified Chinese translation of proposal_en for the
freelancer's private review only; it is never sent to the client. For illegal, policy-violating, account-rental,
review-manipulation, captcha-bypass, or academic-cheating work, recommendation must be "skip".
For every project, rate delivery_clarity, client_reliability, change_risk, five_star_probability, and portfolio_fit
from 0 to 10. change_risk uses 0 for very low scope-change risk and 10 for very high scope-change risk. Give an
overall starter_score from 0 to 10 based on its suitability for earning a high-quality first review; this score is
for prioritization and must never override a safety skip decision."""


MODE_PROMPTS = {
    "starter": """Current operating mode: Starter (first 0–5 completed jobs). Keep every existing safety, keyword,
and project-fit rule. Optimize for a fast, high-quality five-star review rather than maximum profit. Favor small,
clear, low-risk, one-off deliverables that are realistically finishable within 24–48 hours, especially fixed-price
work in the 15–80 USD range (higher budgets remain allowed), estimated under 6 hours, fewer than 20 bids, posted
within 6 hours, payment verified, with a detailed description, attachment, or explicit acceptance criteria.
Boost practical matches for image editing, document formatting/data entry, Chinese translation/proofreading,
small HTML/CSS/landing-page fixes, small Python scripts/automation/API/JSON/CSV/Selenium/scraping bug fixes, and
standard AI tasks. Treat phrases such as need today, quick task, simple fix, minor change, urgent, easy work,
small project, few images, fix only, one page, one issue, and small bug as positive signals.
Reduce recommendation priority for long-term/monthly/full-time/senior/expert/enterprise/team/agency work, large
architecture, large 3D animation or game work, full mobile apps, blockchain, and NFT work. Do not falsely reject a
feasible standard project just because it uses a familiar but unlisted skill.
Recommend a competitive bid near the lower end of the reasonable market range, never an extreme lowball. Give a
delivery promise with a realistic buffer to avoid lateness. The English proposal must not say "I am new". It should
show that the requirements were read, briefly state the solution and deliverables, offer a preview/checkpoint,
state a reasonable revision boundary when appropriate, and emphasize responsive communication. Score the five
review-potential dimensions carefully and make starter_score reflect both review likelihood and scope safety.""",
    "normal": """Current operating mode: Normal. Keep all existing safety, filtering, and practical-delivery rules.
Balance fit, scope clarity, risk, reasonable profit, delivery capacity, and longer-term client value. Do not favor
tiny low-price work merely because it is fast; use the review-potential dimensions as useful context.""",
    "high_value": """Current operating mode: High Value. Keep all existing safety and practical-delivery rules. Favor
well-scoped projects with meaningful budgets, strong technical/design value, repeat-client potential, scalable
architecture, and rates that justify the risk. Small low-price jobs are lower priority unless they offer exceptional
strategic portfolio value. Flag ambiguous enterprise-scale scope for manual review rather than overpromising.""",
}


def build_system_prompt(operating_mode: str | None) -> str:
    mode = normalize_strategy_mode(operating_mode)
    return f"{SYSTEM_PROMPT}\n\n{MODE_PROMPTS[mode]}"


class AnalysisService:
    def __init__(self, db: Session, settings: Settings, provider: OpenAICompatibleProvider | None = None) -> None:
        self.db = db
        self.settings = settings
        self.provider = provider or OpenAICompatibleProvider(settings)

    def analyze_pending(self, limit: int = 20) -> dict[str, int]:
        projects = list(
            self.db.scalars(
                select(Project)
                .where(Project.status == "pending_analysis")
                .order_by(Project.published_at.desc())
                .limit(limit)
            )
        )
        counts = {"requested": len(projects), "analyzed": 0, "failed": 0}
        for project in projects:
            try:
                self.analyze_project(project)
                counts["analyzed"] += 1
            except AIProviderError as exc:
                counts["failed"] += 1
                project.status = "pending_analysis"
                audit(self.db, "analysis_failed", project.id, {"error": str(exc)})
                self.db.commit()
        return counts

    def analyze_project(self, project: Project, force: bool = False) -> ProjectAnalysis:
        if project.analysis and not force:
            return project.analysis
        profile = load_profile(self.settings.profile_path)
        active_count = self.db.scalar(
            select(func.count()).select_from(Project).where(Project.status.in_(["approved", "submitted"]))
        ) or 0
        fallback = self._dry_run_result(project, profile)
        user_prompt = self._build_prompt(project, profile, active_count)
        result, raw = self.provider.analyze(build_system_prompt(self.settings.operating_mode), user_prompt, fallback)
        result, decision_guard = prevent_unsupported_skill_mismatch_skip(result)
        result, priority_adjustment = apply_priority_score(project, result, load_filters(self.settings.filters_path))
        result, strategy = apply_strategy_scoring(project, result, self.settings.operating_mode)
        raw = {**raw, "decision_guard": decision_guard, "strategy": strategy}
        analysis = project.analysis
        if analysis is None:
            analysis = ProjectAnalysis(project=project, **self._analysis_columns(result, raw, priority_adjustment))
            self.db.add(analysis)
        else:
            for key, value in self._analysis_columns(result, raw, priority_adjustment).items():
                setattr(analysis, key, value)
        self._upsert_draft(project, result)
        project.status = "analyzed"
        audit(
            self.db,
            "project_analyzed",
            project.id,
            {
                "score": result.score,
                "recommendation": result.recommendation,
                "operating_mode": strategy["mode"],
                "starter_score": strategy["starter_score"],
            },
        )
        self.db.commit()
        self.db.refresh(analysis)
        return analysis

    def _analysis_columns(
        self, result: Any, raw: dict[str, Any], priority_adjustment: dict[str, Any]
    ) -> dict[str, Any]:
        data = result.model_dump()
        data["priority"] = priority_adjustment
        data["strategy"] = raw.get("strategy", {})
        return {
            "score": result.score,
            "recommendation": result.recommendation,
            "summary_zh": result.summary_zh,
            "proposal_en": result.proposal_en,
            "recommended_bid_amount": result.recommended_bid_amount,
            "currency": result.currency,
            "recommended_delivery_days": result.recommended_delivery_days,
            "effective_hourly_rate": result.effective_hourly_rate,
            "confidence": result.confidence,
            "data": data,
            "raw_response": {**raw, "priority_adjustment": priority_adjustment},
            "error_message": "",
        }

    def _upsert_draft(self, project: Project, result: Any) -> None:
        draft = project.draft
        if draft is None:
            draft = BidDraft(project=project)
            self.db.add(draft)
        if draft.approved_at is None and draft.rejected_at is None:
            draft.proposal_en = result.proposal_en
            draft.bid_amount = result.recommended_bid_amount
            draft.currency = result.currency
            draft.delivery_days = result.recommended_delivery_days

    def _build_prompt(self, project: Project, profile: ProfileConfig, active_count: int) -> str:
        payload = {
            "project": {
                "title": project.title,
                "description": project.description,
                "budget": {"minimum": project.budget_min, "maximum": project.budget_max, "currency": project.currency},
                "type": project.project_type,
                "skills": project.skills,
                "published_at": project.published_at.isoformat() if project.published_at else None,
                "existing_bids": project.bid_count,
                "employer_rating": project.employer_rating,
                "payment_verified": project.payment_verified,
                "employer_history": project.employer_history,
            },
            "freelancer_profile": profile.model_dump(),
            "current_active_project_count": active_count,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _dry_run_result(self, project: Project, profile: ProfileConfig):
        from app.schemas.analysis import AnalysisResult

        blocked_terms = ["academic cheating", "captcha", "account rental", "fake review", "gambling", "adult"]
        text = f"{project.title} {project.description}".lower()
        blocked = next((term for term in blocked_terms if term in text), None)
        budget = project.budget_max or project.budget_min or 0
        hours_min, hours_max = (12, 24) if budget >= 200 else (4, 10)
        rate = round(budget / hours_max, 2) if hours_max else 0
        skills = [skill for skill in profile.skills if skill.lower() in text]
        recommendation = "skip" if blocked else ("bid" if budget >= 100 and project.bid_count <= 30 else "review")
        score = 5 if blocked else min(95, 55 + len(skills) * 8 + (10 if project.payment_verified else 0))
        proposal = "" if blocked else (
            f"Hello,\n\nI reviewed your request for {project.title}. I can build this in clear milestones and keep the work focused on the requested outcome. "
            "Before starting, I would confirm the API access, expected workflows, and acceptance criteria. "
            "I would first deliver a working foundation, then validate the key flows with you before final handover.\n\nBest regards"
        )
        return AnalysisResult(
            score=score,
            recommendation=recommendation,
            summary_zh="本地 dry-run 分析结果；配置 AI 后可获得模型分析。" if not blocked else "检测到高风险或禁止类型的需求，建议跳过。",
            description_zh="本地演示模式未调用翻译模型；配置 AI 后重新分析即可生成完整中文译文。",
            requirements=[project.title],
            skill_match=skills,
            skill_gaps=[] if skills else ["需在投标前确认具体技术细节"],
            estimated_hours_min=hours_min,
            estimated_hours_max=hours_max,
            recommended_bid_amount=round(budget * 0.9, 2) if budget else 0,
            currency=project.currency,
            recommended_delivery_days=max(1, round(hours_max / 6)),
            effective_hourly_rate=rate,
            ai_assistance_ratio=60 if not blocked else 0,
            confidence=55 if not blocked else 95,
            delivery_clarity=7 if not blocked else 0,
            client_reliability=6 if project.payment_verified and not blocked else 4 if not blocked else 0,
            change_risk=4 if not blocked else 10,
            five_star_probability=7 if not blocked else 0,
            portfolio_fit=6 if not blocked else 0,
            starter_score=7 if not blocked else 0,
            risks=["需要在开工前确认范围与验收标准"] if not blocked else [f"检测到禁止关键词：{blocked}"],
            red_flags=[f"禁止或高风险需求：{blocked}"] if blocked else [],
            questions_for_client=["Could you confirm the exact acceptance criteria and any existing API documentation?"] if not blocked else [],
            execution_plan=["Confirm scope", "Implement core workflow", "Test with representative data", "Handover"] if not blocked else [],
            proposal_en=proposal,
            proposal_zh=(
                "您好，\n\n我已查看您的项目需求。我可以采用清晰的里程碑推进工作，并专注于您要求的交付结果。"
                "开始前我会先确认 API 访问、预期工作流程和验收标准；随后交付可运行的基础版本，再与您一起验证关键流程后完成交付。\n\n此致"
                if not blocked else ""
            ),
            reasoning_summary_zh="依据预算、关键词、技能重合度和基础风险规则给出初步建议。",
        )
