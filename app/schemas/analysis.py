from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AnalysisResult(BaseModel):
    """The exact structured contract expected from the configured AI provider."""

    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=0, le=100)
    recommendation: str = Field(pattern="^(bid|review|skip)$")
    summary_zh: str
    description_zh: str = ""
    hard_requirements: list[str] = Field(default_factory=list)
    preferred_options: list[str] = Field(default_factory=list)
    future_roadmap_items: list[str] = Field(default_factory=list)
    hard_skill_mismatch: bool = False
    skill_mismatch_evidence: list[str] = Field(default_factory=list)
    alternative_stack_available: bool = True
    learnable_skills: list[str] = Field(default_factory=list)
    requirements: list[str]
    skill_match: list[str]
    skill_gaps: list[str]
    estimated_hours_min: float = Field(ge=0)
    estimated_hours_max: float = Field(ge=0)
    recommended_bid_amount: float = Field(ge=0)
    currency: str = Field(min_length=1, max_length=16)
    recommended_delivery_days: int = Field(ge=1)
    effective_hourly_rate: float = Field(ge=0)
    ai_assistance_ratio: int = Field(ge=0, le=100)
    confidence: int = Field(ge=0, le=100)
    delivery_clarity: float = Field(default=0, ge=0, le=10)
    client_reliability: float = Field(default=0, ge=0, le=10)
    change_risk: float = Field(default=0, ge=0, le=10)
    five_star_probability: float = Field(default=0, ge=0, le=10)
    portfolio_fit: float = Field(default=0, ge=0, le=10)
    starter_score: float = Field(default=0, ge=0, le=10)
    risks: list[str]
    red_flags: list[str]
    questions_for_client: list[str]
    execution_plan: list[str]
    proposal_en: str
    proposal_zh: str = ""
    reasoning_summary_zh: str

    @model_validator(mode="after")
    def validate_ranges_and_risk(self) -> "AnalysisResult":
        if self.estimated_hours_max < self.estimated_hours_min:
            raise ValueError("estimated_hours_max must be >= estimated_hours_min")
        if self.recommendation == "bid" and not self.proposal_en.strip():
            raise ValueError("bid recommendation requires a non-empty proposal_en")
        if self.hard_skill_mismatch and not self.skill_mismatch_evidence:
            raise ValueError("hard_skill_mismatch requires exact project-description evidence")
        return self
