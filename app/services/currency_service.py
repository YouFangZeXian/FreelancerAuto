from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from app.models import Project


USD_CNY_FALLBACK = 7.20
FX_CACHE_SECONDS = 6 * 60 * 60
FX_URL = "https://api.frankfurter.dev/v1/latest?base=USD&symbols=CNY"
_cached_usd_cny_rate: tuple[float, float, str] | None = None


@dataclass(frozen=True)
class HourlyRateDisplay:
    native_amount: float
    native_currency: str
    usd_amount: float | None
    cny_amount: float | None
    usd_cny_rate: float | None
    rate_source: str


def get_usd_cny_rate() -> tuple[float, str]:
    """Return a cached USD/CNY reference rate, with a local fallback when the public rate feed is unavailable."""
    global _cached_usd_cny_rate
    now = time.monotonic()
    if _cached_usd_cny_rate and now - _cached_usd_cny_rate[0] < FX_CACHE_SECONDS:
        return _cached_usd_cny_rate[1], _cached_usd_cny_rate[2]

    rate = USD_CNY_FALLBACK
    source = "参考汇率"
    try:
        response = httpx.get(FX_URL, timeout=2.5)
        response.raise_for_status()
        fetched = float(response.json()["rates"]["CNY"])
        if fetched > 0:
            rate = fetched
            source = "实时参考汇率"
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        pass

    _cached_usd_cny_rate = (now, rate, source)
    return rate, source


def effective_hourly_rate_display(project: "Project") -> HourlyRateDisplay | None:
    """Convert an AI-provided hourly rate from the project's currency into USD and CNY for display."""
    analysis = project.analysis
    if analysis is None:
        return None

    native_amount = float(analysis.effective_hourly_rate)
    native_currency = (analysis.currency or project.currency or "USD").upper()
    usd_amount = _to_usd(project, native_amount, native_currency)
    if usd_amount is None:
        return HourlyRateDisplay(native_amount, native_currency, None, None, None, "缺少币种汇率")

    usd_cny_rate, rate_source = get_usd_cny_rate()
    return HourlyRateDisplay(
        native_amount=native_amount,
        native_currency=native_currency,
        usd_amount=usd_amount,
        cny_amount=usd_amount * usd_cny_rate,
        usd_cny_rate=usd_cny_rate,
        rate_source=rate_source,
    )


def _to_usd(project: "Project", amount: float, currency: str) -> float | None:
    if currency == "USD":
        return amount
    if currency != project.currency.upper():
        return None

    raw_currency = (project.raw_data or {}).get("currency") or {}
    exchange_rate = _positive_number(raw_currency.get("exchange_rate"))
    if exchange_rate:
        # Freelancer returns the number of project-currency units per USD.
        return amount / exchange_rate

    if project.budget_max and project.budget_usd_max:
        return amount * (project.budget_usd_max / project.budget_max)
    if project.budget_min and project.budget_usd_min:
        return amount * (project.budget_usd_min / project.budget_min)
    return None


def _positive_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
