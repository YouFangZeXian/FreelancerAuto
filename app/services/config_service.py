from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class FilterConfig(BaseModel):
    include_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    priority_keywords: list[str] = Field(default_factory=list)
    priority_score_floor: int = Field(ge=0, le=100, default=90)
    min_budget_usd: float = Field(ge=0, default=0)
    max_budget_usd: float = Field(gt=0, default=2000)
    max_existing_bids: int = Field(ge=0, default=50)
    min_employer_rating: float = Field(ge=0, le=5, default=0)
    require_payment_verified: bool = False
    allowed_project_types: list[str] = Field(default_factory=lambda: ["fixed", "hourly"])

    @field_validator("include_keywords", "exclude_keywords", "priority_keywords", "allowed_project_types")
    @classmethod
    def clean_strings(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item and item.strip()]

    def model_post_init(self, __context: Any) -> None:
        if self.max_budget_usd < self.min_budget_usd:
            raise ValueError("max_budget_usd must be greater than or equal to min_budget_usd")


class ProfileConfig(BaseModel):
    skills: list[str] = Field(default_factory=list)
    preferences: dict[str, list[str]] = Field(default_factory=dict)
    pricing: dict[str, float] = Field(default_factory=dict)
    availability: dict[str, int] = Field(default_factory=dict)


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Configuration file does not exist: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Configuration must be a YAML mapping: {path}")
    return data


def save_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def load_filters(path: Path) -> FilterConfig:
    return FilterConfig.model_validate(load_yaml(path))


def load_profile(path: Path) -> ProfileConfig:
    return ProfileConfig.model_validate(load_yaml(path))
