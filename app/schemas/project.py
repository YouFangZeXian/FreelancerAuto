from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class NormalizedProject(BaseModel):
    freelancer_project_id: int
    title: str
    description: str = ""
    project_url: str = ""
    currency: str = "USD"
    project_type: str = ""
    budget_min: float | None = None
    budget_max: float | None = None
    budget_usd_min: float | None = None
    budget_usd_max: float | None = None
    published_at: datetime | None = None
    bid_count: int = 0
    employer_id: int | None = None
    employer_rating: float | None = None
    payment_verified: bool | None = None
    employer_history: dict[str, Any] = Field(default_factory=dict)
    skills: list[str] = Field(default_factory=list)
    raw_data: dict[str, Any] = Field(default_factory=dict)

