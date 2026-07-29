from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import Settings
from app.schemas.project import NormalizedProject

logger = logging.getLogger(__name__)


class FreelancerAPIError(RuntimeError):
    pass


class FreelancerClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._client = client or httpx.Client(timeout=30.0, follow_redirects=True)

    def _headers(self) -> dict[str, str]:
        if not self.settings.freelancer_access_token:
            return {}
        return {"freelancer-oauth-v1": self.settings.freelancer_access_token}

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._client.request(
                method,
                f"{self.settings.freelancer_api_url}{path}",
                headers=self._headers(),
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise FreelancerAPIError(f"Freelancer API network error: {exc.__class__.__name__}") from exc
        if response.status_code >= 400:
            try:
                message = response.json().get("message", response.text)
            except ValueError:
                message = response.text
            raise FreelancerAPIError(f"Freelancer API {response.status_code}: {message[:500]}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise FreelancerAPIError("Freelancer API returned non-JSON data") from exc
        if payload.get("status") == "error":
            raise FreelancerAPIError(str(payload.get("message", "Freelancer API error")))
        return payload

    def test_connection(self) -> dict[str, Any]:
        if self.settings.freelancer_mock_mode:
            return {"ok": True, "mode": "mock", "user": {"id": 9001, "display_name": "Mock Freelancer"}}
        payload = self._request("GET", "/users/0.1/self/")
        return {"ok": True, "mode": "live", "user": payload.get("result", {})}

    def get_self(self) -> dict[str, Any]:
        if self.settings.freelancer_mock_mode:
            return {"id": self.settings.freelancer_bidder_id or 9001, "display_name": "Mock Freelancer"}
        return self._request("GET", "/users/0.1/self/").get("result", {})

    def search_active_projects(
        self,
        query: str = "",
        project_types: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
        from_time: int | None = None,
    ) -> list[dict[str, Any]]:
        if self.settings.freelancer_mock_mode:
            return mock_projects()[max(offset, 0):max(offset, 0) + max(limit, 1)]

        requested = max(limit, 1)
        page_size = 100  # Freelancer's active-project endpoint accepts at most 100 records per request.
        collected: list[dict[str, Any]] = []
        seen_ids: set[int | str] = set()
        current_offset = max(offset, 0)
        while len(collected) < requested:
            params: list[tuple[str, Any]] = [
                ("limit", min(page_size, requested - len(collected))),
                ("offset", current_offset),
                ("full_description", "true"),
                ("job_details", "true"),
                ("user_details", "true"),
                ("owner_info", "true"),
                ("user_employer_reputation", "true"),
                ("user_financial_details", "true"),
                ("sort_field", "time_updated"),
            ]
            if query:
                params.append(("query", query))
            if from_time:
                params.append(("from_time", from_time))
            for project_type in project_types or ["fixed", "hourly"]:
                params.append(("project_types[]", project_type))
            payload = self._request("GET", "/projects/0.1/projects/active/", params=params)
            result = payload.get("result", {})
            users = result.get("users", {})
            page = result.get("projects", [])
            for project in page:
                project_id = project.get("id")
                if project_id in seen_ids:
                    continue
                seen_ids.add(project_id)
                project["users"] = users
                collected.append(project)
            if len(page) < page_size:
                break
            current_offset += page_size
        return collected

    def get_project(self, project_id: int) -> dict[str, Any]:
        if self.settings.freelancer_mock_mode:
            for project in mock_projects():
                if int(project["id"]) == project_id:
                    return project
            raise FreelancerAPIError(f"Mock project {project_id} was not found")
        params = {
            "full_description": "true",
            "job_details": "true",
            "user_details": "true",
            "owner_info": "true",
            "user_employer_reputation": "true",
            "user_financial_details": "true",
        }
        result = self._request("GET", f"/projects/0.1/projects/{project_id}/", params=params).get("result", {})
        if "project" in result and isinstance(result["project"], dict):
            project = result["project"]
            project["users"] = result.get("users", {})
            return project
        return result

    def submit_bid(
        self,
        project_id: int,
        bidder_id: int,
        amount: float,
        period: int,
        proposal: str,
    ) -> dict[str, Any]:
        payload = {
            "project_id": project_id,
            "bidder_id": bidder_id,
            "amount": amount,
            "period": period,
            "description": proposal,
            "milestone_percentage": 100,
        }
        return self._request("POST", "/projects/0.1/bids/", json=payload).get("result", {})


def normalize_project(raw: dict[str, Any], base_url: str) -> NormalizedProject:
    budget = raw.get("budget") or {}
    currency = raw.get("currency") or {}
    owner = raw.get("owner") or raw.get("owner_info") or raw.get("user") or {}
    users = raw.get("users") or {}
    owner_id = raw.get("owner_id") or owner.get("id")
    if not owner and owner_id is not None:
        owner = users.get(str(owner_id), users.get(owner_id, {})) or {}
    jobs = raw.get("jobs") or raw.get("job_details") or []
    skills = [str(job.get("name") or job.get("localized_name") or job.get("id")) for job in jobs if isinstance(job, dict)]
    exchange_rate = _number(currency.get("exchange_rate")) or 1.0
    minimum = _number(budget.get("minimum"))
    maximum = _number(budget.get("maximum"))
    timestamp = raw.get("time_submitted") or raw.get("submitdate") or raw.get("time_updated")
    published_at = datetime.fromtimestamp(int(timestamp), tz=timezone.utc) if timestamp else None
    employer_reputation = owner.get("employer_reputation") or owner.get("reputation") or {}
    rating = _number(employer_reputation.get("overall") if isinstance(employer_reputation, dict) else employer_reputation)
    payment_verified = _bool_or_none(
        owner.get("payment_verified")
        or owner.get("financial_details", {}).get("payment_verified")
        or raw.get("payment_verified")
    )
    bid_stats = raw.get("bid_stats") or {}
    project_id = int(raw["id"])
    seo_url = raw.get("seo_url")
    project_url = f"{base_url.rstrip('/')}/projects/{seo_url}/" if seo_url else f"{base_url.rstrip('/')}/projects/{project_id}/"
    return NormalizedProject(
        freelancer_project_id=project_id,
        title=str(raw.get("title") or "Untitled project"),
        description=str(raw.get("description") or raw.get("preview_description") or ""),
        project_url=project_url,
        currency=str(currency.get("code") or "USD"),
        project_type=str(raw.get("type") or ""),
        budget_min=minimum,
        budget_max=maximum,
        budget_usd_min=(minimum / exchange_rate) if minimum is not None else None,
        budget_usd_max=(maximum / exchange_rate) if maximum is not None else None,
        published_at=published_at,
        bid_count=int(bid_stats.get("bid_count") or raw.get("bid_count") or 0),
        employer_id=int(owner_id) if owner_id is not None else None,
        employer_rating=rating,
        payment_verified=payment_verified,
        employer_history={
            "project_count": owner.get("project_count"),
            "reviews": employer_reputation if isinstance(employer_reputation, dict) else {},
        },
        skills=skills,
        raw_data=raw,
    )


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def mock_projects() -> list[dict[str, Any]]:
    """Representative local data that enables an end-to-end dry run without credentials."""
    now = int(datetime.now(timezone.utc).timestamp())
    return [
        {
            "id": 1000001,
            "title": "Build a FastAPI automation dashboard",
            "description": "Need a small Python FastAPI admin dashboard that calls an external API, stores results, and sends notifications.",
            "type": "fixed",
            "status": "active",
            "frontend_project_status": "open",
            "time_submitted": now - 1800,
            "seo_url": "python/build-fastapi-automation-dashboard",
            "budget": {"minimum": 300, "maximum": 700},
            "currency": {"code": "USD", "exchange_rate": 1},
            "bid_stats": {"bid_count": 8},
            "jobs": [{"name": "Python"}, {"name": "FastAPI"}, {"name": "API"}],
            "owner": {
                "id": 200001,
                "payment_verified": True,
                "employer_reputation": {"overall": 4.8, "reviews": 18},
                "project_count": 22,
            },
        },
        {
            "id": 1000002,
            "title": "Academic cheating service request",
            "description": "Need someone to complete an assessed assignment and guarantee a passing grade.",
            "type": "fixed",
            "status": "active",
            "frontend_project_status": "open",
            "time_submitted": now - 900,
            "seo_url": "writing/academic-cheating-request",
            "budget": {"minimum": 150, "maximum": 300},
            "currency": {"code": "USD", "exchange_rate": 1},
            "bid_stats": {"bid_count": 2},
            "jobs": [{"name": "Writing"}],
            "owner": {"id": 200002, "payment_verified": False, "employer_reputation": {"overall": 3.0}},
        },
        {
            "id": 1000003,
            "title": "Solve a captcha automatically",
            "description": "Need a script to bypass captcha verification on third-party sites.",
            "type": "hourly",
            "status": "active",
            "frontend_project_status": "open",
            "time_submitted": now - 300,
            "seo_url": "automation/solve-captcha",
            "budget": {"minimum": 20, "maximum": 40},
            "currency": {"code": "USD", "exchange_rate": 1},
            "bid_stats": {"bid_count": 6},
            "jobs": [{"name": "Automation"}],
            "owner": {"id": 200003, "payment_verified": True, "employer_reputation": {"overall": 4.0}},
        },
    ]
