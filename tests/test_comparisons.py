import math
from datetime import date

import pandas as pd

from src.comparisons import (
    day_over_day_range, week_over_week_range, filter_date_range, compare,
    compare_week_over_week,
)


def _row(d, impressions, clicks, spend, conversions, conversion_value):
    return {
        "date": d, "campaign": "Test Campaign", "impressions": impressions,
        "clicks": clicks, "spend": spend, "conversions": conversions,
        "conversion_value": conversion_value,
    }


def test_day_over_day_range_is_two_consecutive_days(campaigns_df):
    cur_start, cur_end, prev_start, prev_end = day_over_day_range(campaigns_df)
    assert cur_start == cur_end
    assert prev_start == prev_end
    assert (cur_start - prev_start).days == 1


def test_week_over_week_range_is_two_non_overlapping_seven_day_windows(campaigns_df):
    cur_start, cur_end, prev_start, prev_end = week_over_week_range(campaigns_df)
    assert (cur_end - cur_start).days == 6
    assert (prev_end - prev_start).days == 6
    assert prev_end < cur_start


def test_compare_computes_absolute_and_percent_change():
    current_df = pd.DataFrame([_row(date(2026, 1, 2), 1000, 100, 200.0, 10, 500.0)])
    previous_df = pd.DataFrame([_row(date(2026, 1, 1), 800, 80, 160.0, 8, 400.0)])
    result = compare(current_df, previous_df, group_by=None).iloc[0]

    assert result["clicks_abs_change"] == 20
    assert round(result["clicks_pct_change"], 4) == 0.25


def test_compare_handles_zero_previous_value_without_crashing():
    current_df = pd.DataFrame([_row(date(2026, 1, 2), 1000, 100, 200.0, 10, 500.0)])
    previous_df = pd.DataFrame([_row(date(2026, 1, 1), 0, 0, 0.0, 0, 0.0)])
    result = compare(current_df, previous_df, group_by=None).iloc[0]

    assert result["clicks_abs_change"] == 100
    # Percent change from zero is undefined -- should be NaN, not a crash or inf.
    assert math.isnan(result["clicks_pct_change"])


def test_compare_by_campaign_groups_correctly():
    current_df = pd.DataFrame([
        {"date": date(2026, 1, 2), "campaign": "A", "impressions": 100, "clicks": 10,
         "spend": 20.0, "conversions": 1, "conversion_value": 50.0},
        {"date": date(2026, 1, 2), "campaign": "B", "impressions": 200, "clicks": 20,
         "spend": 40.0, "conversions": 2, "conversion_value": 100.0},
    ])
    previous_df = pd.DataFrame([
        {"date": date(2026, 1, 1), "campaign": "A", "impressions": 100, "clicks": 10,
         "spend": 20.0, "conversions": 1, "conversion_value": 50.0},
        {"date": date(2026, 1, 1), "campaign": "B", "impressions": 100, "clicks": 10,
         "spend": 20.0, "conversions": 1, "conversion_value": 50.0},
    ])
    result = compare(current_df, previous_df, group_by="campaign").set_index("campaign")
    assert result.loc["A", "clicks_abs_change"] == 0
    assert result.loc["B", "clicks_abs_change"] == 10


def test_compare_week_over_week_runs_on_real_data_without_error(campaigns_df):
    result = compare_week_over_week(campaigns_df, group_by="campaign")
    assert not result.empty
    assert "conversions_pct_change" in result.columns
