from __future__ import annotations

from dataclasses import dataclass

from app.schemas.project import NormalizedProject
from app.services.config_service import FilterConfig


@dataclass(frozen=True)
class FilterDecision:
    accepted: bool
    reason: str


class FilterService:
    HARD_DENY_TERMS = {
        "academic cheating",
        "exam cheating",
        "captcha",
        "account rental",
        "fake review",
        "review manipulation",
        "money laundering",
    }

    def __init__(self, rules: FilterConfig) -> None:
        self.rules = rules

    def evaluate(self, project: NormalizedProject) -> FilterDecision:
        text = " ".join([project.title, project.description, *project.skills]).lower()
        hard_denied = next((term for term in self.HARD_DENY_TERMS if term in text), None)
        if hard_denied:
            return FilterDecision(False, f"Hard-deny policy matched: {hard_denied}")
        excluded = next((term for term in self.rules.exclude_keywords if term.lower() in text), None)
        if excluded:
            return FilterDecision(False, f"Excluded keyword matched: {excluded}")

        if self.rules.include_keywords and not any(term.lower() in text for term in self.rules.include_keywords):
            return FilterDecision(False, "No include keyword matched")

        if project.project_type and project.project_type.lower() not in {item.lower() for item in self.rules.allowed_project_types}:
            return FilterDecision(False, f"Project type {project.project_type} is not allowed")

        budget_max = project.budget_usd_max if project.budget_usd_max is not None else project.budget_usd_min
        if budget_max is not None and budget_max < self.rules.min_budget_usd:
            return FilterDecision(False, f"Budget ${budget_max:.2f} is below minimum")
        budget_min = project.budget_usd_min if project.budget_usd_min is not None else project.budget_usd_max
        if budget_min is not None and budget_min > self.rules.max_budget_usd:
            return FilterDecision(False, f"Budget ${budget_min:.2f} is above maximum")

        if project.bid_count > self.rules.max_existing_bids:
            return FilterDecision(False, f"Existing bids ({project.bid_count}) exceed the limit")
        if project.employer_rating is not None and project.employer_rating < self.rules.min_employer_rating:
            return FilterDecision(False, f"Employer rating ({project.employer_rating:.1f}) is below minimum")
        if self.rules.require_payment_verified and project.payment_verified is not True:
            return FilterDecision(False, "Employer payment is not verified")
        return FilterDecision(True, "Passed local rules")
