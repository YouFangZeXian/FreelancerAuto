from types import SimpleNamespace

from app.services.currency_service import effective_hourly_rate_display


def test_effective_hourly_rate_converts_project_currency_to_usd_and_cny(monkeypatch) -> None:
    project = SimpleNamespace(
        currency="EUR",
        raw_data={"currency": {"exchange_rate": 0.8}},
        budget_min=80,
        budget_max=160,
        budget_usd_min=100,
        budget_usd_max=200,
        analysis=SimpleNamespace(effective_hourly_rate=40, currency="EUR"),
    )
    monkeypatch.setattr("app.services.currency_service.get_usd_cny_rate", lambda: (7.2, "实时参考汇率"))

    display = effective_hourly_rate_display(project)

    assert display is not None
    assert display.usd_amount == 50
    assert display.cny_amount == 360
    assert display.native_currency == "EUR"


def test_effective_hourly_rate_uses_usd_directly(monkeypatch) -> None:
    project = SimpleNamespace(
        currency="USD",
        raw_data={"currency": {"exchange_rate": 1}},
        budget_min=100,
        budget_max=200,
        budget_usd_min=100,
        budget_usd_max=200,
        analysis=SimpleNamespace(effective_hourly_rate=30, currency="USD"),
    )
    monkeypatch.setattr("app.services.currency_service.get_usd_cny_rate", lambda: (7.2, "实时参考汇率"))

    display = effective_hourly_rate_display(project)

    assert display is not None
    assert display.usd_amount == 30
    assert display.cny_amount == 216
