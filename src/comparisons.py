"""
Period comparisons: day-over-day, week-over-week, and arbitrary
period-over-period. This module only slices dates and computes
absolute/percent change -- all the underlying math comes from
src/metrics.py so there is exactly one implementation of "how do we
calculate CTR" in the whole codebase.
"""

from datetime import timedelta

import pandas as pd

from src.metrics import aggregate, ALL_METRICS, safe_div


def latest_date(df):
    return df["date"].max()


def day_over_day_range(df):
    """Return (current_start, current_end, previous_start, previous_end)
    for the most recent day vs. the day before it."""
    current = latest_date(df)
    previous = current - timedelta(days=1)
    return current, current, previous, previous


def week_over_week_range(df):
    """Return the most recent 7-day window vs. the 7 days before that."""
    current_end = latest_date(df)
    current_start = current_end - timedelta(days=6)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=6)
    return current_start, current_end, previous_start, previous_end


def filter_date_range(df, start, end):
    return df[(df["date"] >= start) & (df["date"] <= end)]


def compare(current_df, previous_df, group_by=None):
    """Aggregate both periods and return a tidy DataFrame with one row per
    group (or one row total, if group_by is None) and, for every metric,
    a `<metric>_current`, `<metric>_previous`, `<metric>_abs_change`, and
    `<metric>_pct_change` column.

    Percent change is safely handled when the previous value is zero
    (returns None rather than raising or showing infinity).
    """
    current_agg = aggregate(current_df, group_by=group_by)
    previous_agg = aggregate(previous_df, group_by=group_by)

    if group_by is None:
        # Single account-level row on each side -- no key column to join on,
        # just line the two single-row tables up side by side.
        merged = pd.concat(
            [current_agg.add_suffix("_current"), previous_agg.add_suffix("_previous")], axis=1
        ).fillna(0)
    else:
        key_cols = group_by if isinstance(group_by, list) else [group_by]
        merged = current_agg.merge(
            previous_agg, on=key_cols, how="outer", suffixes=("_current", "_previous")
        ).fillna(0)

    for metric in ALL_METRICS:
        cur = merged[f"{metric}_current"]
        prev = merged[f"{metric}_previous"]
        merged[f"{metric}_abs_change"] = cur - prev
        merged[f"{metric}_pct_change"] = safe_div(cur - prev, prev, default=float("nan"))

    return merged


def compare_day_over_day(df, group_by=None):
    cur_start, cur_end, prev_start, prev_end = day_over_day_range(df)
    current_df = filter_date_range(df, cur_start, cur_end)
    previous_df = filter_date_range(df, prev_start, prev_end)
    return compare(current_df, previous_df, group_by=group_by)


def compare_week_over_week(df, group_by=None):
    cur_start, cur_end, prev_start, prev_end = week_over_week_range(df)
    current_df = filter_date_range(df, cur_start, cur_end)
    previous_df = filter_date_range(df, prev_start, prev_end)
    return compare(current_df, previous_df, group_by=group_by)
