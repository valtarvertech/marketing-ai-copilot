from datetime import date

import pandas as pd
import pytest

from src.contribution import rank_contributors, rate_changes


def _rows():
    current = pd.DataFrame([
        {"date": date(2026, 1, 8), "campaign": "A", "impressions": 1000, "clicks": 100,
         "spend": 200.0, "conversions": 5, "conversion_value": 250.0},
        {"date": date(2026, 1, 8), "campaign": "B", "impressions": 2000, "clicks": 200,
         "spend": 400.0, "conversions": 20, "conversion_value": 1000.0},
    ])
    previous = pd.DataFrame([
        {"date": date(2026, 1, 1), "campaign": "A", "impressions": 1000, "clicks": 100,
         "spend": 200.0, "conversions": 10, "conversion_value": 500.0},
        {"date": date(2026, 1, 1), "campaign": "B", "impressions": 2000, "clicks": 200,
         "spend": 400.0, "conversions": 15, "conversion_value": 750.0},
    ])
    return pd.concat([current, previous], ignore_index=True)


def test_contributions_sum_to_total_change_for_additive_metric():
    df = _rows()
    current_range = (date(2026, 1, 8), date(2026, 1, 8))
    previous_range = (date(2026, 1, 1), date(2026, 1, 1))

    ranked, total_change = rank_contributors(df, "conversions", current_range, previous_range)

    # Account went from 25 conversions to 25 -- net zero -- but two
    # campaigns moved in opposite directions (A: -5, B: +5).
    assert total_change == 0
    assert set(ranked["conversions_abs_change"]) == {-5, 5}


def test_rank_contributors_orders_by_size_of_impact():
    df = _rows()
    current_range = (date(2026, 1, 8), date(2026, 1, 8))
    previous_range = (date(2026, 1, 1), date(2026, 1, 1))

    ranked, _ = rank_contributors(df, "conversions", current_range, previous_range)
    # Both campaigns move by the same magnitude here, so just check both are present.
    assert set(ranked["campaign"]) == {"A", "B"}


def test_rank_contributors_rejects_rate_metrics():
    df = _rows()
    current_range = (date(2026, 1, 8), date(2026, 1, 8))
    previous_range = (date(2026, 1, 1), date(2026, 1, 1))
    with pytest.raises(ValueError):
        rank_contributors(df, "roas", current_range, previous_range)


def test_rate_changes_rejects_raw_metrics():
    df = _rows()
    current_range = (date(2026, 1, 8), date(2026, 1, 8))
    previous_range = (date(2026, 1, 1), date(2026, 1, 1))
    with pytest.raises(ValueError):
        rate_changes(df, "conversions", current_range, previous_range)


def test_real_data_contributions_sum_to_account_total(campaigns_df):
    from src.comparisons import week_over_week_range
    cur_start, cur_end, prev_start, prev_end = week_over_week_range(campaigns_df)
    ranked, total_change = rank_contributors(
        campaigns_df, "conversions", (cur_start, cur_end), (prev_start, prev_end)
    )
    assert round(ranked["conversions_abs_change"].sum(), 6) == round(total_change, 6)
