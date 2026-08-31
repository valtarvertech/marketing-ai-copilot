from datetime import date

import pandas as pd

from src.change_intelligence import changes_before_date, performance_around_change


def _campaign_row(d, campaign, conversions, spend=100.0, clicks=50, impressions=500, conversion_value=None):
    return {
        "date": d, "campaign": campaign, "impressions": impressions, "clicks": clicks,
        "spend": spend, "conversions": conversions,
        "conversion_value": conversion_value if conversion_value is not None else conversions * 50.0,
    }


def test_changes_before_date_only_includes_lookback_window():
    changes = pd.DataFrame([
        {"date": date(2026, 1, 1), "campaign": "A", "entity": "Budget", "change_type": "budget_decreased",
         "old_value": "100", "new_value": "80", "changed_by": "x", "notes": "n"},
        {"date": date(2026, 1, 10), "campaign": "A", "entity": "Budget", "change_type": "budget_decreased",
         "old_value": "80", "new_value": "60", "changed_by": "x", "notes": "n"},
    ])
    result = changes_before_date(changes, "A", date(2026, 1, 12), lookback_days=5)
    assert len(result) == 1
    assert result.iloc[0]["date"] == date(2026, 1, 10)


def test_performance_around_change_computes_before_after_correctly():
    campaigns = pd.DataFrame(
        [_campaign_row(date(2026, 1, d), "A", conversions=10) for d in range(1, 8)]
        + [_campaign_row(date(2026, 1, d), "A", conversions=20) for d in range(9, 16)]
    )
    result = performance_around_change(campaigns, "A", date(2026, 1, 8), window_days=7)
    assert result["has_data"]
    assert result["before"]["conversions"] == 70
    assert result["after"]["conversions"] == 140


def test_performance_around_change_reports_no_data_when_window_is_empty():
    campaigns = pd.DataFrame([_campaign_row(date(2026, 1, 1), "A", conversions=10)])
    result = performance_around_change(campaigns, "A", date(2026, 6, 1), window_days=7)
    assert not result["has_data"]


def test_performance_around_change_does_not_mix_other_campaigns():
    campaigns = pd.DataFrame([
        _campaign_row(date(2026, 1, 5), "A", conversions=10),
        _campaign_row(date(2026, 1, 5), "B", conversions=999),
        _campaign_row(date(2026, 1, 10), "A", conversions=15),
    ])
    result = performance_around_change(campaigns, "A", date(2026, 1, 8), window_days=7)
    assert result["before"]["conversions"] == 10
    assert result["after"]["conversions"] == 15
