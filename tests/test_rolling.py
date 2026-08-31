from datetime import date, timedelta

import pandas as pd
import pytest

from src.rolling import (
    rolling_8_day_dates, rolling_8_day_range, compare_rolling_8_day,
    build_daily_monitoring_table, daily_average,
    latest_day_vs_prior_average, same_weekday_average, generate_8day_brief,
    rolling_week_ranges, format_date_range, build_weekly_matrix,
    weekly_pct_change_matrix, classify_weekly_trend, generate_5week_brief,
    split_contributors, split_rate_movers,
)
from src.contribution import rank_contributors, rate_changes


def _row(d, impressions=1000, clicks=100, spend=100.0, conversions=10, conversion_value=500.0, campaign="X"):
    return {
        "date": d, "campaign": campaign, "impressions": impressions, "clicks": clicks,
        "spend": spend, "conversions": conversions, "conversion_value": conversion_value,
    }


# ---------------------------------------------------------------------------
# Rolling-window date logic
# ---------------------------------------------------------------------------
def test_rolling_8_day_dates_are_8_consecutive_dates_ending_at_max_date(campaigns_df):
    dates = rolling_8_day_dates(campaigns_df)
    assert len(dates) == 8
    assert dates[-1] == campaigns_df["date"].max()
    assert dates == sorted(dates)
    assert (dates[-1] - dates[0]).days == 7


def test_rolling_8_day_dates_never_hardcoded_shifts_with_data():
    df_a = pd.DataFrame([_row(date(2026, 1, 10))])
    df_b = pd.DataFrame([_row(date(2026, 3, 1))])
    dates_a = rolling_8_day_dates(df_a)
    dates_b = rolling_8_day_dates(df_b)
    assert dates_a[-1] == date(2026, 1, 10)
    assert dates_b[-1] == date(2026, 3, 1)
    assert dates_a != dates_b


def test_rolling_8_day_range_is_two_equal_length_non_overlapping_blocks(campaigns_df):
    cur_start, cur_end, prev_start, prev_end = rolling_8_day_range(campaigns_df)
    assert cur_end == campaigns_df["date"].max()
    assert (cur_end - cur_start).days == 7
    assert (prev_end - prev_start).days == 7
    assert prev_end + timedelta(days=1) == cur_start  # back-to-back, no gap or overlap


def test_compare_rolling_8_day_matches_hand_computed_totals():
    dates_current = [date(2026, 1, d) for d in range(9, 17)]  # 8 days
    dates_previous = [date(2026, 1, d) for d in range(1, 9)]  # 8 days before that
    rows = [_row(d, conversions=10) for d in dates_previous] + [_row(d, conversions=15) for d in dates_current]
    df = pd.DataFrame(rows)

    result = compare_rolling_8_day(df, group_by=None).iloc[0]
    assert result["conversions_current"] == 15 * 8
    assert result["conversions_previous"] == 10 * 8
    assert round(result["conversions_pct_change"], 4) == 0.5


def test_build_daily_monitoring_table_has_metrics_as_rows_dates_as_columns():
    dates = [date(2026, 1, d) for d in range(1, 4)]
    rows = [_row(dates[0], conversions=5), _row(dates[1], conversions=8), _row(dates[2], conversions=12)]
    table = build_daily_monitoring_table(pd.DataFrame(rows), dates)
    assert list(table.columns) == dates
    assert table.loc["conversions"].tolist() == [5, 8, 12]


# ---------------------------------------------------------------------------
# Five-week construction
# ---------------------------------------------------------------------------
def test_rolling_week_ranges_are_5_non_overlapping_adjacent_windows(campaigns_df):
    ranges = rolling_week_ranges(campaigns_df, num_weeks=5)
    assert len(ranges) == 5
    assert ranges[-1][1] == campaigns_df["date"].max()
    for start, end in ranges:
        assert (end - start).days == 6
    # Adjacent windows must be back-to-back with no gap and no overlap.
    for i in range(4):
        assert ranges[i][1] + timedelta(days=1) == ranges[i + 1][0]


def test_rolling_week_ranges_shift_with_latest_date_not_hardcoded():
    df = pd.DataFrame([_row(date(2026, 5, 15))])
    ranges = rolling_week_ranges(df, num_weeks=5)
    assert ranges[-1] == (date(2026, 5, 9), date(2026, 5, 15))
    assert ranges[0] == (date(2026, 4, 11), date(2026, 4, 17))


def test_format_date_range_same_month():
    assert format_date_range(date(2026, 8, 2), date(2026, 8, 8)) == "Aug 2–8"


def test_format_date_range_crosses_month_boundary():
    label = format_date_range(date(2026, 7, 29), date(2026, 8, 4))
    assert "Jul 29" in label and "Aug 4" in label


def test_build_weekly_matrix_columns_match_formatted_ranges():
    ranges = [(date(2026, 8, 2), date(2026, 8, 8)), (date(2026, 8, 9), date(2026, 8, 15))]
    rows = [_row(date(2026, 8, 2), conversions=10), _row(date(2026, 8, 9), conversions=20)]
    matrix = build_weekly_matrix(pd.DataFrame(rows), ranges)
    assert list(matrix.columns) == ["Aug 2–8", "Aug 9–15"]
    assert matrix.loc["conversions"].tolist() == [10, 20]


def test_weekly_pct_change_matrix_first_column_is_nan_and_rest_compute_correctly():
    ranges = [(date(2026, 8, 2), date(2026, 8, 8)), (date(2026, 8, 9), date(2026, 8, 15))]
    rows = [_row(date(2026, 8, 2), conversions=10), _row(date(2026, 8, 9), conversions=15)]
    matrix = build_weekly_matrix(pd.DataFrame(rows), ranges)
    pct = weekly_pct_change_matrix(matrix)
    assert pd.isna(pct.loc["conversions", "Aug 2–8"])
    assert round(pct.loc["conversions", "Aug 9–15"], 4) == 0.5


# ---------------------------------------------------------------------------
# Latest-day-vs-7-day-baseline calculations
# ---------------------------------------------------------------------------
def test_daily_average_divides_raw_metrics_by_number_of_days():
    dates = [date(2026, 1, d) for d in range(1, 8)]
    rows = [_row(d, conversions=14, spend=140.0) for d in dates]
    avg = daily_average(pd.DataFrame(rows), dates)
    assert avg.iloc[0]["conversions"] == 14  # 7 days * 14 summed / 7 = 14
    assert avg.iloc[0]["spend"] == 140.0


def test_latest_day_vs_prior_average_known_values():
    prior_dates = [date(2026, 1, d) for d in range(1, 8)]
    latest = date(2026, 1, 8)
    rows = [_row(d, conversions=10, spend=100.0) for d in prior_dates]
    rows.append(_row(latest, conversions=20, spend=100.0))  # conversions doubled on the latest day
    df = pd.DataFrame(rows)

    result = latest_day_vs_prior_average(df)
    row = result["table"].iloc[0]
    assert result["latest_date"] == latest
    assert result["prior_range"] == (date(2026, 1, 1), date(2026, 1, 7))
    assert row["conversions_latest"] == 20
    assert row["conversions_prior_avg"] == 10
    assert row["conversions_abs_change"] == 10
    assert round(row["conversions_pct_change"], 4) == 1.0


def test_same_weekday_average_only_uses_matching_weekday_dates():
    # Jan 3, 2026 is a Saturday. Build 4 prior Saturdays plus a bunch of
    # non-Saturday noise, and confirm only the Saturdays are averaged.
    target = date(2026, 1, 31)  # also a Saturday
    saturdays = [target - timedelta(days=7 * i) for i in range(1, 5)]
    rows = [_row(d, conversions=100) for d in saturdays]
    rows += [_row(target - timedelta(days=i), conversions=999) for i in range(1, 6) if (target - timedelta(days=i)) not in saturdays]
    df = pd.DataFrame(rows)

    avg, used = same_weekday_average(df, target, lookback_weeks=4)
    assert set(used) == set(saturdays)
    assert avg.iloc[0]["conversions"] == 100


def test_8day_brief_does_not_swallow_a_single_candidate_signal():
    # Regression test for a real bug: when exactly one primary metric moves
    # materially, min() and max() of a 1-item candidate pool return the
    # same item, and a naive "can't be both worst and best" check nulled
    # out the only signal, silently reporting "Stable" instead.
    dates = [date(2026, 1, d) for d in range(1, 8)]
    rows = [_row(d, conversions=10, spend=100.0, conversion_value=500.0) for d in dates]
    # Latest day: spend doubles (CPA doubles -> clearly unfavorable), but
    # conversion_value also doubles so ROAS stays flat -- isolates CPA as
    # the only materially-moved primary metric.
    rows.append(_row(date(2026, 1, 8), conversions=10, spend=200.0, conversion_value=1000.0))
    df = pd.DataFrame(rows)

    brief = generate_8day_brief(df)
    assert brief["overall"] == "Unfavorable"
    assert "CPA" in brief["summary"]


def test_8day_brief_real_data_smoke(campaigns_df):
    brief = generate_8day_brief(campaigns_df)
    assert brief["overall"] in {"Favorable", "Unfavorable", "Mixed", "Stable"}
    assert isinstance(brief["summary"], str) and len(brief["summary"]) > 0


# ---------------------------------------------------------------------------
# Weekly trend classification
# ---------------------------------------------------------------------------
def test_classify_weekly_trend_sustained_increase():
    result = classify_weekly_trend([100, 108, 115, 122, 130], "conversions")
    assert result["pattern"] == "sustained"
    assert result["direction"] == "increasing"
    assert result["favorability"] == "Favorable"


def test_classify_weekly_trend_sustained_increase_is_unfavorable_for_lower_is_better_metric():
    result = classify_weekly_trend([50, 55, 60, 65, 70], "cpa")
    assert result["pattern"] == "sustained"
    assert result["favorability"] == "Unfavorable"


def test_classify_weekly_trend_single_week_fluctuation():
    result = classify_weekly_trend([100, 101, 99, 100, 130], "conversions")
    assert result["pattern"] == "single_week"


def test_classify_weekly_trend_flat():
    result = classify_weekly_trend([100, 101, 99, 102, 101], "conversions")
    assert result["pattern"] == "flat"


def test_5week_brief_real_data_smoke(campaigns_df):
    brief = generate_5week_brief(campaigns_df)
    assert brief["overall"] in {"Favorable", "Unfavorable", "Mixed", "Stable"}
    assert len(brief["week_ranges"]) == 5


# ---------------------------------------------------------------------------
# Contribution calculations (additive vs. ratio metrics)
# ---------------------------------------------------------------------------
def _two_campaign_rows():
    current = [
        _row(date(2026, 1, 8), campaign="A", conversions=5, spend=200.0, conversion_value=250.0),
        _row(date(2026, 1, 8), campaign="B", conversions=25, spend=200.0, conversion_value=1250.0),
    ]
    previous = [
        _row(date(2026, 1, 1), campaign="A", conversions=10, spend=200.0, conversion_value=500.0),
        _row(date(2026, 1, 1), campaign="B", conversions=15, spend=200.0, conversion_value=750.0),
    ]
    return pd.concat([pd.DataFrame(current), pd.DataFrame(previous)], ignore_index=True)


def test_split_contributors_separates_detractors_from_offsets():
    df = _two_campaign_rows()
    current_range = (date(2026, 1, 8), date(2026, 1, 8))
    previous_range = (date(2026, 1, 1), date(2026, 1, 1))
    ranked, total_change = rank_contributors(df, "conversions", current_range, previous_range)

    detractors, offsets = split_contributors(ranked, "conversions")
    assert total_change == 5  # -5 (A) + 10 (B)
    assert detractors["campaign"].tolist() == ["A"]
    assert offsets["campaign"].tolist() == ["B"]
    assert (detractors["conversions_abs_change"] < 0).all()
    assert (offsets["conversions_abs_change"] > 0).all()


def test_split_rate_movers_honors_lower_is_better_direction():
    # Campaign A: CPA rises (spend flat, conversions fall) -> deteriorates.
    # Campaign B: CPA falls (spend flat, conversions rise) -> improves.
    df = _two_campaign_rows()
    current_range = (date(2026, 1, 8), date(2026, 1, 8))
    previous_range = (date(2026, 1, 1), date(2026, 1, 1))
    rc = rate_changes(df, "cpa", current_range, previous_range)

    deteriorating, improving = split_rate_movers(rc, "cpa")
    assert deteriorating["campaign"].tolist() == ["A"]
    assert improving["campaign"].tolist() == ["B"]


def test_split_rate_movers_honors_higher_is_better_direction():
    df = _two_campaign_rows()
    current_range = (date(2026, 1, 8), date(2026, 1, 8))
    previous_range = (date(2026, 1, 1), date(2026, 1, 1))
    rc = rate_changes(df, "roas", current_range, previous_range)

    deteriorating, improving = split_rate_movers(rc, "roas")
    # A: conversion_value halved, spend flat -> ROAS falls -> deteriorates.
    # B: conversion_value up, spend flat -> ROAS rises -> improves.
    assert deteriorating["campaign"].tolist() == ["A"]
    assert improving["campaign"].tolist() == ["B"]


def test_split_rate_movers_filters_out_immaterial_moves():
    df = _two_campaign_rows()
    current_range = (date(2026, 1, 8), date(2026, 1, 8))
    previous_range = (date(2026, 1, 1), date(2026, 1, 1))
    rc = rate_changes(df, "cpa", current_range, previous_range)

    deteriorating, improving = split_rate_movers(rc, "cpa", materiality=2.0)  # nothing moves >=200%
    assert deteriorating.empty
    assert improving.empty
