from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.ai.provider import OpenAICompatibleProvider
from app.clients.freelancer import FreelancerClient
from app.clients.ntfy import NtfyClient
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import AuditLog, BidSubmission, Project
from app.services.analysis_service import AnalysisService
from app.services.bid_service import BidSafetyError, BidService
from app.services.config_service import FilterConfig, ProfileConfig, load_filters, load_profile, save_yaml
from app.services.cycle_service import CycleService
from app.services.currency_service import effective_hourly_rate_display
from app.services.project_service import ProjectService
from app.services.runtime_settings import effective_settings, get_runtime_settings, update_runtime_settings
from app.services.strategy_service import (
    OPERATING_MODES,
    get_strategy_meta,
    normalize_strategy_mode,
    starter_progress,
    stored_starter_score,
)


templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
router = APIRouter()

STATUS_LABELS = {
    "discovered": "已发现",
    "filtered_out": "已筛除",
    "pending_analysis": "待分析",
    "analyzed": "已分析",
    "notified": "已通知",
    "approved": "已批准",
    "rejected": "已拒绝",
    "submitted": "已提交",
    "submission_failed": "提交失败",
    "manual_submission_required": "需手动投标",
    "pending": "处理中",
    "failed": "失败",
    "dry_run": "模拟提交",
    "sent": "已发送",
    "skipped": "已跳过",
}
RECOMMENDATION_LABELS = {"bid": "建议投标", "review": "人工复核", "skip": "建议跳过"}
PROJECT_TYPE_LABELS = {"fixed": "固定价格", "hourly": "按小时"}
MODE_LABELS = {
    "mock": "模拟模式",
    "live": "正式模式",
    "dry-run": "试运行",
}
EVENT_LABELS = {
    "analysis_failed": "AI 分析失败",
    "project_analyzed": "项目分析完成",
    "bid_approved": "投标草稿已批准",
    "bid_rejected": "项目已拒绝",
    "manual_submission_required": "已转为手动投标",
    "bid_dry_run": "投标试运行",
    "bid_submission_failed": "投标提交失败",
    "bid_submitted": "投标已提交",
    "project_hard_denied": "项目触发硬性否决",
    "project_discovered": "发现新项目",
    "notification_sent": "通知已发送",
    "notification_failed": "通知发送失败",
}
ACTOR_LABELS = {
    "system": "系统",
    "web-user": "网页用户",
    "cli-user": "命令行用户",
}


def _filter_reason_label(value: str | None) -> str:
    if not value:
        return "暂无筛选结果记录"
    exact = {
        "No include keyword matched": "未匹配任何包含关键词",
        "Employer payment is not verified": "雇主付款方式未验证",
        "Passed local rules": "已通过本地筛选规则",
    }
    if value in exact:
        return exact[value]
    patterns = (
        (r"^Hard-deny policy matched: (.+)$", "触发硬性否决规则：{}"),
        (r"^Excluded keyword matched: (.+)$", "匹配排除关键词：{}"),
        (r"^Project type (.+) is not allowed$", "不允许的项目类型：{}"),
        (r"^Budget \$(.+) is below minimum$", "预算 ${} 低于最低限额"),
        (r"^Budget \$(.+) is above maximum$", "预算 ${} 高于最高限额"),
        (r"^Existing bids \((.+)\) exceed the limit$", "现有投标数（{}）超过上限"),
        (r"^Employer rating \((.+)\) is below minimum$", "雇主评分（{}）低于最低要求"),
    )
    for pattern, template in patterns:
        match = re.match(pattern, value)
        if match:
            return template.format(*match.groups())
    return value


templates.env.globals.update(
    status_label=lambda value: STATUS_LABELS.get(value, value),
    recommendation_label=lambda value: RECOMMENDATION_LABELS.get(value, value),
    project_type_label=lambda value: PROJECT_TYPE_LABELS.get(value, value),
    mode_label=lambda value: MODE_LABELS.get(value, value),
    event_label=lambda value: EVENT_LABELS.get(value, value),
    actor_label=lambda value: ACTOR_LABELS.get(value, value),
    filter_reason_label=_filter_reason_label,
)


def _context(request: Request, **values):
    return {"request": request, "settings": get_settings(), **values}


def _redirect(path: str, message: str, kind: str = "success") -> RedirectResponse:
    return RedirectResponse(f"{path}?message={quote(message)}&kind={quote(kind)}", status_code=303)


def _optional_int_query(value: str, field_name: str, *, minimum: int, maximum: int) -> int | None:
    """Parse an optional numeric filter without treating an empty form field as an error."""
    value = value.strip()
    if not value:
        return None
    try:
        number = int(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{field_name} 必须是整数") from exc
    if not minimum <= number <= maximum:
        raise HTTPException(status_code=422, detail=f"{field_name} 必须在 {minimum} 到 {maximum} 之间")
    return number


def _optional_float_query(value: str, field_name: str, *, minimum: float) -> float | None:
    """Parse an optional decimal filter without treating an empty form field as an error."""
    value = value.strip()
    if not value:
        return None
    try:
        number = float(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{field_name} 必须是数字") from exc
    if number < minimum:
        raise HTTPException(status_code=422, detail=f"{field_name} 不能小于 {minimum}")
    return number


def _project_or_404(db: Session, project_id: int) -> Project:
    project = db.scalars(
        select(Project)
        .where(Project.freelancer_project_id == project_id)
        .options(joinedload(Project.analysis), joinedload(Project.draft), joinedload(Project.submissions))
    ).unique().first()
    if not project:
        raise HTTPException(status_code=404, detail="未找到项目")
    return project


@router.get("/")
@router.get("/projects")
def dashboard(
    request: Request,
    status: str = "",
    recommendation: str = "",
    min_score: str = "",
    budget_min: str = "",
    notified: str = "",
    reviewed: str = "",
    submitted: str = "",
    q: str = "",
    db: Session = Depends(get_db),
):
    effective = effective_settings(db, get_settings())
    operating_mode = normalize_strategy_mode(effective.operating_mode)
    min_score_value = _optional_int_query(min_score, "最低评分", minimum=0, maximum=100)
    budget_min_value = _optional_float_query(budget_min, "最低预算", minimum=0)
    statement = select(Project).options(joinedload(Project.analysis), joinedload(Project.draft))
    if status:
        statement = statement.where(Project.status == status)
    if q:
        statement = statement.where(or_(Project.title.ilike(f"%{q}%"), Project.description.ilike(f"%{q}%")))
    if budget_min_value is not None:
        statement = statement.where(Project.budget_usd_max >= budget_min_value)
    if notified in {"yes", "no"}:
        statement = statement.where(Project.notified.is_(notified == "yes"))
    if reviewed in {"yes", "no"}:
        statement = statement.where(Project.reviewed.is_(reviewed == "yes"))
    projects = list(db.scalars(statement.order_by(Project.published_at.desc())).unique())
    if recommendation:
        projects = [p for p in projects if p.analysis and p.analysis.recommendation == recommendation]
    if min_score_value is not None:
        projects = [p for p in projects if p.analysis and p.analysis.score >= min_score_value]
    if submitted in {"yes", "no"}:
        projects = [p for p in projects if (p.status == "submitted") == (submitted == "yes")]
    if status == "analyzed":
        # The database query is already newest-first; stable sort keeps that order for equal values.
        if operating_mode == "starter":
            projects.sort(
                key=lambda project: (
                    stored_starter_score(project),
                    project.analysis.score if project.analysis else -1,
                ),
                reverse=True,
            )
        elif operating_mode == "high_value":
            projects.sort(
                key=lambda project: (
                    project.analysis.score if project.analysis else -1,
                    project.budget_usd_max or project.budget_usd_min or 0,
                ),
                reverse=True,
            )
        else:
            projects.sort(key=lambda project: project.analysis.score if project.analysis else -1, reverse=True)
    stats = {
        "total": db.query(Project).count(),
        "pending": db.query(Project).filter(Project.status == "pending_analysis").count(),
        "review": db.query(Project).filter(Project.status.in_(["analyzed", "notified", "approved"])).count(),
        "submitted": db.query(Project).filter(Project.status == "submitted").count(),
    }
    return templates.TemplateResponse(
        request,
        "projects.html",
        _context(
            request,
            projects=projects,
            stats=stats,
            effective=effective,
            strategy=get_strategy_meta(operating_mode),
            operating_modes=OPERATING_MODES,
            starter_progress=starter_progress(effective.starter_review_count, effective.starter_completed_projects),
            filters={
                "status": status, "recommendation": recommendation, "min_score": min_score_value,
                "budget_min": budget_min_value, "notified": notified, "reviewed": reviewed,
                "submitted": submitted, "q": q,
            },
        ),
    )


@router.post("/settings/strategy")
def save_strategy(
    operating_mode: str = Form(default="starter"),
    starter_review_count: int = Form(default=0),
    starter_completed_projects: int = Form(default=0),
    db: Session = Depends(get_db),
):
    mode = normalize_strategy_mode(operating_mode)
    if operating_mode != mode:
        return _redirect("/projects", "未知的运营模式，未保存", "error")
    if starter_review_count < 0 or starter_completed_projects < 0:
        return _redirect("/projects", "破零进度不能小于 0", "error")
    update_runtime_settings(
        db,
        {
            "operating_mode": mode,
            "starter_review_count": starter_review_count,
            "starter_completed_projects": starter_completed_projects,
        },
    )
    return _redirect("/projects", f"已切换为 {get_strategy_meta(mode)['short_label']}")


@router.get("/projects/{project_id}")
def project_detail(request: Request, project_id: int, db: Session = Depends(get_db)):
    project = _project_or_404(db, project_id)
    return templates.TemplateResponse(
        request,
        "project_detail.html",
        _context(request, project=project, hourly_rate=effective_hourly_rate_display(project)),
    )


@router.post("/projects/{project_id}/analyze")
def analyze_project(project_id: int, force: bool = Form(default=False), db: Session = Depends(get_db)):
    project = _project_or_404(db, project_id)
    settings = effective_settings(db, get_settings())
    try:
        AnalysisService(db, settings).analyze_project(project, force=force)
        return _redirect(f"/projects/{project_id}", "AI 分析已完成")
    except Exception as exc:
        return _redirect(f"/projects/{project_id}", str(exc), "error")


@router.post("/projects/{project_id}/draft")
def update_draft(
    project_id: int,
    proposal_en: str = Form(...),
    bid_amount: float = Form(...),
    delivery_days: int = Form(...),
    db: Session = Depends(get_db),
):
    project = _project_or_404(db, project_id)
    if not project.draft:
        return _redirect(f"/projects/{project_id}", "请先运行 AI 分析，再编辑投标草稿", "error")
    project.draft.proposal_en = proposal_en.strip()
    project.draft.bid_amount = bid_amount
    project.draft.delivery_days = delivery_days
    project.draft.approved_at = None
    if project.status == "approved":
        project.status = "analyzed"
    db.commit()
    return _redirect(f"/projects/{project_id}", "草稿已保存，原批准状态已撤销")


@router.post("/projects/{project_id}/approve")
def approve_project(project_id: int, db: Session = Depends(get_db)):
    project = _project_or_404(db, project_id)
    try:
        BidService(db, effective_settings(db, get_settings())).approve(project, actor="web-user")
        return _redirect(f"/projects/{project_id}", "草稿已批准；真正提交前仍需二次确认")
    except BidSafetyError as exc:
        return _redirect(f"/projects/{project_id}", str(exc), "error")


@router.post("/projects/{project_id}/reject")
def reject_project(project_id: int, reason: str = Form(default=""), db: Session = Depends(get_db)):
    project = _project_or_404(db, project_id)
    try:
        BidService(db, effective_settings(db, get_settings())).reject(project, reason, actor="web-user")
        return _redirect(f"/projects/{project_id}", "项目已拒绝")
    except BidSafetyError as exc:
        return _redirect(f"/projects/{project_id}", str(exc), "error")


@router.post("/projects/{project_id}/manual")
def manual_project(project_id: int, db: Session = Depends(get_db)):
    project = _project_or_404(db, project_id)
    try:
        BidService(db, effective_settings(db, get_settings())).mark_manual(project, actor="web-user")
        return _redirect(f"/projects/{project_id}", "已标记为手动投标")
    except BidSafetyError as exc:
        return _redirect(f"/projects/{project_id}", str(exc), "error")


@router.post("/projects/{project_id}/submit")
def submit_project(project_id: int, confirmation: str = Form(default=""), db: Session = Depends(get_db)):
    project = _project_or_404(db, project_id)
    try:
        BidService(db, effective_settings(db, get_settings())).submit(
            project, confirm=confirmation.strip().upper() == "SUBMIT", dry_run=False, actor="web-user"
        )
        return _redirect(f"/projects/{project_id}", "Bid 已成功提交")
    except BidSafetyError as exc:
        return _redirect(f"/projects/{project_id}", str(exc), "error")


@router.post("/actions/fetch")
def fetch_action(db: Session = Depends(get_db)):
    settings = effective_settings(db, get_settings())
    result = ProjectService(db, settings).fetch_projects()
    analysis = AnalysisService(db, settings).analyze_pending(limit=settings.analysis_batch_limit)
    return _redirect(
        "/projects",
        "抓取并分析完成：收到 {fetched} 个，新增 {new} 个，跳过已存在 {known_skipped} 个，待分析 {pending_analysis} 个，已筛除 {filtered_out} 个；已分析 {analyzed} 个，失败 {failed} 个。".format(
            **result, analyzed=analysis["analyzed"], failed=analysis["failed"]
        ),
    )


@router.post("/actions/analyze")
def analyze_action(db: Session = Depends(get_db)):
    settings = effective_settings(db, get_settings())
    result = AnalysisService(db, settings).analyze_pending(limit=settings.analysis_batch_limit)
    return _redirect(
        "/projects",
        "批量分析完成：已分析 {analyzed} 个，失败 {failed} 个".format(**result),
    )


@router.post("/actions/cycle")
def cycle_action(db: Session = Depends(get_db)):
    result = CycleService(db, effective_settings(db, get_settings())).run()
    fetch = result["fetch"]
    analysis = result["analysis"]
    return _redirect(
        "/projects",
        "完整周期执行完成：抓取 {fetched} 个（新增 {new}、更新 {updated}、待分析 {pending_analysis}、筛除 {filtered_out}）；"
        "分析 {analyzed} 个（失败 {failed}）；通知 {notified} 个".format(
            **fetch,
            analyzed=analysis["analyzed"],
            failed=analysis["failed"],
            notified=result["notified"],
        ),
    )


@router.get("/history/bids")
def bid_history(request: Request, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(BidSubmission).options(joinedload(BidSubmission.project)).order_by(BidSubmission.created_at.desc())
    ).unique().all()
    return templates.TemplateResponse(request, "bid_history.html", _context(request, submissions=rows))


@router.get("/logs")
def logs(request: Request, db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(500)).all()
    return templates.TemplateResponse(request, "logs.html", _context(request, logs=rows))


@router.get("/settings/filters")
def filters_settings(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "settings_filters.html", _context(request, config=load_filters(get_settings().filters_path)))


@router.post("/settings/filters")
def save_filters(
    include_keywords: str = Form(default=""), exclude_keywords: str = Form(default=""),
    priority_keywords: str = Form(default=""), priority_score_floor: int = Form(default=90),
    min_budget_usd: float = Form(...), max_budget_usd: float = Form(...), max_existing_bids: int = Form(...),
    min_employer_rating: float = Form(...), require_payment_verified: bool = Form(default=False),
    allowed_project_types: list[str] = Form(default=[]), db: Session = Depends(get_db),
):
    try:
        config = FilterConfig(
            include_keywords=_lines(include_keywords), exclude_keywords=_lines(exclude_keywords),
            priority_keywords=_lines(priority_keywords), priority_score_floor=priority_score_floor,
            min_budget_usd=min_budget_usd, max_budget_usd=max_budget_usd, max_existing_bids=max_existing_bids,
            min_employer_rating=min_employer_rating, require_payment_verified=require_payment_verified,
            allowed_project_types=allowed_project_types,
        )
        save_yaml(get_settings().filters_path, config.model_dump())
        return _redirect("/settings/filters", "筛选规则已保存")
    except Exception as exc:
        return _redirect("/settings/filters", str(exc), "error")


@router.get("/settings/profile")
def profile_settings(request: Request):
    return templates.TemplateResponse(request, "settings_profile.html", _context(request, profile=load_profile(get_settings().profile_path)))


@router.post("/settings/profile")
def save_profile(
    skills: str = Form(default=""), preferred_projects: str = Form(default=""), avoid_projects: str = Form(default=""),
    target_hourly_rate_usd: float = Form(...), minimum_effective_hourly_rate_usd: float = Form(...),
    max_active_projects: int = Form(...), available_hours_per_week: int = Form(...),
):
    try:
        profile = ProfileConfig(
            skills=_lines(skills),
            preferences={"preferred_projects": _lines(preferred_projects), "avoid_projects": _lines(avoid_projects)},
            pricing={"target_hourly_rate_usd": target_hourly_rate_usd, "minimum_effective_hourly_rate_usd": minimum_effective_hourly_rate_usd},
            availability={"max_active_projects": max_active_projects, "available_hours_per_week": available_hours_per_week},
        )
        save_yaml(get_settings().profile_path, profile.model_dump())
        return _redirect("/settings/profile", "个人能力画像已保存")
    except Exception as exc:
        return _redirect("/settings/profile", str(exc), "error")


@router.get("/settings/integrations")
def integration_settings(request: Request, db: Session = Depends(get_db)):
    runtime = get_runtime_settings(db)
    effective = effective_settings(db, get_settings())
    status = {
        "freelancer": effective.is_freelancer_configured,
        "freelancer_mode": "mock" if effective.freelancer_mock_mode else "live",
        "ai": effective.is_ai_configured,
        "ai_mode": "dry-run" if effective.ai_dry_run else "live",
        "ntfy": bool(effective.ntfy_topic),
        "bid_enabled": effective.freelancer_bid_submission_enabled,
    }
    return templates.TemplateResponse(
        request, "settings_integrations.html", _context(request, runtime=runtime, effective=effective, status=status)
    )


@router.post("/settings/integrations")
def save_integrations(
    ai_base_url: str = Form(default=""), ai_model: str = Form(default=""), ai_timeout_seconds: int = Form(...),
    notify_score_threshold: int = Form(...), scheduler_interval_minutes: int = Form(...),
    freelancer_fetch_limit: int = Form(default=300), analysis_batch_limit: int = Form(default=300), db: Session = Depends(get_db),
):
    try:
        update_runtime_settings(db, locals())
        return _redirect("/settings/integrations", "非敏感运行设置已保存")
    except Exception as exc:
        return _redirect("/settings/integrations", str(exc), "error")


@router.post("/actions/test/{target}")
def test_integration(target: str, db: Session = Depends(get_db)):
    settings = effective_settings(db, get_settings())
    try:
        if target == "ai":
            result = OpenAICompatibleProvider(settings).test_connection()
        elif target == "freelancer":
            result = FreelancerClient(settings).test_connection()
        elif target == "ntfy":
            result = NtfyClient(settings).test_connection()
        else:
            raise HTTPException(status_code=404, detail="未知集成服务")
        return _redirect("/settings/integrations", f"{target} 连接测试：{result}", "success" if result.get("ok") else "error")
    except Exception as exc:
        return _redirect("/settings/integrations", f"{target} 连接测试失败：{exc}", "error")


def _lines(value: str) -> list[str]:
    return [item.strip() for line in value.splitlines() for item in line.split(",") if item.strip()]
