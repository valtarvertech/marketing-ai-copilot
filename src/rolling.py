"""
Rolling-window monitoring: the deterministic logic behind Performance
Intelligence's "Rolling 8 Days" and "Rolling 5 Weeks" views.

Every window here is computed relative to the latest date actually
present in the data (`df["date"].max()`) -- never a hard-coded date.
That's deliberate: when the synthetic CSVs are eventually replaced with
a live API feed, "the latest complete day" will just be a different
date and everything in this module keeps working unchanged.

Two comparisons that don't already exist elsewhere in the app live here:

  - latest_day_vs_prior_average(): a single day vs. the *daily average*
    of the preceding 7 days (distinct from comparisons.day_over_day,
    which compares two single days, and comparisons.week_over_week,
    which compares two 7-day totals).
  - same_weekday_average(): the average of the last few occurrences of
    the same weekday, used to tell "this is just a normal Saturday"
    apart from a real deviation.
"""

from datetime import timedelta

import numpy as np
import pandas as pd

from src.metrics import RAW_METRICS, ALL_METRICS, METRIC_DIRECTION, safe_div, aggregate
from src.comparisons import filter_date_range, compare

MATERIALITY = 0.05  # consistent with the rest of the app (executive_brief, investigation)

METRIC_LABELS = {
    "impressions": "impressions", "clicks": "clicks", "spend": "spend",
    "conversions": "conversions", "conversion_value": "conversion value",
    "ctr": "CTR", "cpc": "CPC", "conversion_rate": "conversion rate",
    "cpa": "CPA", "roas": "ROAS",
}
PRIMARY_METRICS = ["conversions", "roas", "conversion_rate", "cpa", "cpc"]


def _format_date(d):
    return f"{d.strftime('%A, %b')} {d.day}"


def format_date_range(start, end):
    """'Aug 2–8' style label; falls back to a fuller form across a month boundary."""
    if start.month == end.month and start.year == end.year:
        return f"{start.strftime('%b')} {start.day}–{end.day}"
    return f"{start.strftime('%b')} {start.day} – {end.strftime('%b')} {end.day}"


def latest_complete_date(df):
    return df["date"].max()


# ---------------------------------------------------------------------------
# Rolling 8 Days
# ---------------------------------------------------------------------------
def rolling_8_day_dates(df):
    """The 8 most recent dates in the dataset, oldest first."""
    latest = latest_complete_date(df)
    return [latest - timedelta(days=i) for i in range(7, -1, -1)]


def rolling_8_day_range(df):
    """(current_start, current_end, previous_start, previous_end) for the
    latest 8-day block vs. the immediately preceding, equal-length
    (non-overlapping) 8-day block. Distinct from a week-over-week
    comparison (7 days) and from latest_day_vs_prior_average() (1 day vs.
    a trailing daily average) -- this is "two whole 8-day periods,
    back to back"."""
    latest = latest_complete_date(df)
    current_start = latest - timedelta(days=7)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=7)
    return current_start, latest, previous_start, previous_end


def compare_rolling_8_day(df, group_by=None):
    cur_start, cur_end, prev_start, prev_end = rolling_8_day_range(df)
    return compare(filter_date_range(df, cur_start, cur_end), filter_date_range(df, prev_start, prev_end), group_by=group_by)


def build_daily_monitoring_table(df, dates):
    """Metrics-as-rows, dates-as-columns table of account-level daily values."""
    rows = {}
    for d in dates:
        day_df = df[df["date"] == d]
        agg = aggregate(day_df, group_by=None)
        rows[d] = agg.iloc[0][ALL_METRICS] if not agg.empty else pd.Series(0.0, index=ALL_METRICS)
    return pd.DataFrame(rows)[dates]  # keep column order oldest->newest


def daily_average(df, dates, group_by=None):
    """Average per-day value across an arbitrary set of dates. Raw metrics
    (impressions, clicks, ...) are divided by how many of those dates
    actually have data; ratio metrics are left as the blended rate
    computed from the summed numerator/denominator, which is already
    the correct multi-day average (see src/metrics.py's aggregation rule)."""
    subset = df[df["date"].isin(dates)]
    n = subset["date"].nunique()
    agg = aggregate(subset, group_by=group_by)
    if n > 0:
        for metric in RAW_METRICS:
            agg[metric] = agg[metric] / n
    return agg


def _diff_aggregated(current_agg, baseline_agg, group_by, current_suffix, baseline_suffix):
    """Same shape as comparisons.compare(), but takes two already-aggregated
    frames instead of two raw slices -- needed because "prior 7-day
    average" isn't itself the output of aggregate() on a single slice."""
    if group_by is None:
        merged = pd.concat(
            [current_agg.add_suffix(current_suffix), baseline_agg.add_suffix(baseline_suffix)], axis=1
        ).fillna(0)
    else:
        key_cols = group_by if isinstance(group_by, list) else [group_by]
        merged = current_agg.merge(
            baseline_agg, on=key_cols, how="outer", suffixes=(current_suffix, baseline_suffix)
        ).fillna(0)

    for metric in ALL_METRICS:
        cur = merged[f"{metric}{current_suffix}"]
        base = merged[f"{metric}{baseline_suffix}"]
        merged[f"{metric}_abs_change"] = cur - base
        merged[f"{metric}_pct_change"] = safe_div(cur - base, base, default=float("nan"))
    return merged


def latest_day_vs_prior_average(df, group_by=None):
    """Compare the latest complete day against the daily average of the
    preceding 7 calendar days. Returns a dict with the diff table plus
    the exact dates involved, so the UI can show its work."""
    latest = latest_complete_date(df)
    prior_dates = [latest - timedelta(days=i) for i in range(1, 8)]

    latest_agg = aggregate(df[df["date"] == latest], group_by=group_by)
    prior_avg = daily_average(df, prior_dates, group_by=group_by)

    table = _diff_aggregated(latest_agg, prior_avg, group_by, "_latest", "_prior_avg")
    return {
        "table": table,
        "latest_date": latest,
        "prior_range": (min(prior_dates), max(prior_dates)),
    }


def same_weekday_average(df, target_date, lookback_weeks=4, group_by=None):
    """Average of the last `lookback_weeks` occurrences of target_date's
    weekday (not including target_date itself), for telling normal
    weekly seasonality apart from a real change."""
    candidates = [target_date - timedelta(days=7 * i) for i in range(1, lookback_weeks + 1)]
    available_dates = set(df["date"])
    used = [d for d in candidates if d in available_dates]
    return daily_average(df, used, group_by=group_by), used


def generate_8day_brief(df):
    """Deterministic narrative for the Rolling 8 Days view: how the latest
    complete day compares to the trailing 7-day average, filtering out
    moves that are just normal day-of-week seasonality."""
    diff = latest_day_vs_prior_average(df)
    row = diff["table"].iloc[0]
    latest_date = diff["latest_date"]
    weekday_name = latest_date.strftime("%A")

    same_wd_avg, used_dates = same_weekday_average(df, latest_date)
    same_wd_row = same_wd_avg.iloc[0] if not same_wd_avg.empty else None

    candidates, dow_explained = [], []
    for metric in PRIMARY_METRICS:
        pct_vs_avg = row[f"{metric}_pct_change"]
        if pct_vs_avg is None or pd.isna(pct_vs_avg) or abs(pct_vs_avg) < MATERIALITY:
            continue

        explained = False
        if same_wd_row is not None and used_dates:
            latest_val = row[f"{metric}_latest"]
            same_wd_val = same_wd_row[metric]
            pct_vs_same_wd = safe_div(latest_val - same_wd_val, same_wd_val, default=float("nan"))
            if not pd.isna(pct_vs_same_wd):
                # "Explained by day-of-week" if the deviation from this
                # weekday's own recent history is small outright, OR is at
                # least half the size of the deviation from the blended
                # 7-day average (i.e. normal weekday/weekend mix accounts
                # for most of the apparent gap).
                if abs(pct_vs_same_wd) < MATERIALITY or abs(pct_vs_same_wd) <= abs(pct_vs_avg) * 0.5:
                    explained = True

        if explained:
            dow_explained.append(metric)
            continue

        direction = METRIC_DIRECTION.get(metric, "neutral")
        impact = pct_vs_avg if direction == "higher_is_better" else -pct_vs_avg
        candidates.append((metric, pct_vs_avg, impact))

    # Partition by sign first, then pick the extreme of each side -- picking
    # min()/max() of the whole pool first and only then discarding
    # same-metric or wrong-sign results would incorrectly null out the only
    # signal when just one candidate exists (min and max of a 1-item list
    # are the same item).
    unfavorable = [c for c in candidates if c[2] < 0]
    favorable = [c for c in candidates if c[2] > 0]
    worst = min(unfavorable, key=lambda c: c[2]) if unfavorable else None
    best = max(favorable, key=lambda c: c[2]) if favorable else None

    parts = []
    if worst is not None:
        metric, pct, _ = worst
        parts.append(
            f"{METRIC_LABELS[metric]} is {abs(pct):.0%} {'above' if pct > 0 else 'below'} "
            f"its trailing 7-day average, which is unfavorable"
        )
    if best is not None:
        metric, pct, _ = best
        parts.append(
            f"{METRIC_LABELS[metric]} is {abs(pct):.0%} {'above' if pct > 0 else 'below'} "
            f"its trailing 7-day average, which is favorable"
        )

    if not parts:
        overall = "Stable"
        summary = f"On {_format_date(latest_date)}, no metric deviates materially from its trailing 7-day average."
    else:
        overall = "Mixed" if (worst is not None and best is not None) else ("Unfavorable" if worst is not None else "Favorable")
        summary = (
            f"On {_format_date(latest_date)}, performance vs. the trailing 7-day average was "
            f"{overall.lower()}: " + "; ".join(parts) + "."
        )

    if dow_explained:
        summary += (
            f" Movement in {', '.join(METRIC_LABELS[m] for m in dow_explained)} looks consistent with "
            f"typical {weekday_name} patterns rather than a new issue."
        )

    return {"overall": overall, "summary": summary, "latest_date": latest_date, "dow_explained": dow_explained}


# ---------------------------------------------------------------------------
# Rolling 5 Weeks
# ---------------------------------------------------------------------------
def rolling_week_ranges(df, num_weeks=5):
    """The `num_weeks` most recent complete, non-overlapping 7-day windows,
    oldest first, the newest ending on the latest complete date."""
    latest = latest_complete_date(df)
    ranges = []
    end = latest
    for _ in range(num_weeks):
        start = end - timedelta(days=6)
        ranges.append((start, end))
        end = start - timedelta(days=1)
    return list(reversed(ranges))


def build_weekly_matrix(df, week_ranges):
    """Metrics-as-rows, week-label-as-columns table of account-level
    weekly totals/blended rates."""
    rows = {}
    for start, end in week_ranges:
        agg = aggregate(filter_date_range(df, start, end), group_by=None)
        label = format_date_range(start, end)
        rows[label] = agg.iloc[0][ALL_METRICS] if not agg.empty else pd.Series(0.0, index=ALL_METRICS)
    labels = [format_date_range(s, e) for s, e in week_ranges]
    return pd.DataFrame(rows)[labels]


def weekly_pct_change_matrix(matrix_df):
    """Percent change of each displayed week vs. the immediately preceding
    displayed week (first column has no preceding week, so it's NaN)."""
    cols = matrix_df.columns.tolist()
    pct = pd.DataFrame(index=matrix_df.index, columns=cols, dtype=float)
    pct[cols[0]] = np.nan
    for i in range(1, len(cols)):
        prev_col, cur_col = cols[i - 1], cols[i]
        pct[cur_col] = safe_div(matrix_df[cur_col] - matrix_df[prev_col], matrix_df[prev_col], default=np.nan)
    return pct


def classify_weekly_trend(values, metric, materiality=MATERIALITY):
    """Classify a metric's week-by-week values (oldest -> newest) as a
    sustained trend, a single-week fluctuation, volatile, or flat, and
    translate that into Favorable/Unfavorable using METRIC_DIRECTION.
    `values` should have at least 2 points."""
    values = list(values)
    diffs = [values[i + 1] - values[i] for i in range(len(values) - 1)]

    overall_pct = safe_div(values[-1] - values[0], values[0], default=None)
    if overall_pct is None or pd.isna(overall_pct) or abs(overall_pct) < materiality:
        pattern, direction = "flat", "flat"
    else:
        direction = "increasing" if overall_pct > 0 else "decreasing"
        sign = 1 if overall_pct > 0 else -1

        # Check "is this really just the latest week jumping?" BEFORE
        # checking "did most weeks agree on direction?" -- otherwise a
        # single large move plus several tiny same-signed noise steps
        # would satisfy the direction-agreement check and get mislabeled
        # "sustained" even though nothing happened before the last week.
        other_diffs_total = sum(abs(d) for d in diffs[:-1])
        if abs(diffs[-1]) > other_diffs_total:
            pattern = "single_week"
        else:
            agreeing = sum(1 for d in diffs if (d > 0 and sign > 0) or (d < 0 and sign < 0))
            pattern = "sustained" if agreeing >= len(diffs) - 1 else "volatile"

    metric_direction = METRIC_DIRECTION.get(metric, "neutral")
    if metric_direction == "neutral" or pattern == "flat":
        favorability_label = "Flat" if pattern == "flat" else "Neutral"
    elif metric_direction == "higher_is_better":
        favorability_label = "Favorable" if direction == "increasing" else "Unfavorable"
    else:
        favorability_label = "Favorable" if direction == "decreasing" else "Unfavorable"

    return {
        "pattern": pattern, "direction": direction,
        "overall_pct_change": overall_pct, "favorability": favorability_label,
    }


def generate_5week_brief(df, num_weeks=5):
    week_ranges = rolling_week_ranges(df, num_weeks)
    matrix = build_weekly_matrix(df, week_ranges)

    findings = {}
    for metric in PRIMARY_METRICS:
        findings[metric] = classify_weekly_trend(matrix.loc[metric].tolist(), metric)

    sustained_bad = [(m, r) for m, r in findings.items() if r["pattern"] == "sustained" and r["favorability"] == "Unfavorable"]
    sustained_good = [(m, r) for m, r in findings.items() if r["pattern"] == "sustained" and r["favorability"] == "Favorable"]
    single_week_bad = [(m, r) for m, r in findings.items() if r["pattern"] == "single_week" and r["favorability"] == "Unfavorable"]

    trend_phrase = {"increasing": "an upward trend", "decreasing": "a downward trend"}

    parts = []
    if sustained_bad:
        metric, r = max(sustained_bad, key=lambda x: abs(x[1]["overall_pct_change"]))
        parts.append(
            f"{METRIC_LABELS[metric]} has been on {trend_phrase.get(r['direction'], 'a sustained trend')} "
            f"across the window ({r['overall_pct_change']:+.0%} from the first week to the latest), "
            f"which is unfavorable"
        )
    if sustained_good:
        metric, r = max(sustained_good, key=lambda x: abs(x[1]["overall_pct_change"]))
        parts.append(
            f"{METRIC_LABELS[metric]} has sustained {trend_phrase.get(r['direction'], 'a trend')} "
            f"({r['overall_pct_change']:+.0%}), which is favorable"
        )
    if not sustained_bad and not sustained_good and single_week_bad:
        metric, r = single_week_bad[0]
        parts.append(
            f"the latest week's move in {METRIC_LABELS[metric]} looks like a one-week fluctuation, "
            f"not a sustained trend"
        )

    window_label = f"{format_date_range(*week_ranges[0])} to {format_date_range(*week_ranges[-1])}"
    if not parts:
        overall = "Stable"
        summary = f"No metric shows a meaningful sustained trend across {window_label}."
    else:
        overall = "Mixed" if (sustained_bad and sustained_good) else (
            "Unfavorable" if sustained_bad else ("Favorable" if sustained_good else "Mixed")
        )
        summary = f"Across {window_label}, performance has been {overall.lower()}: " + "; ".join(parts) + "."

    return {"overall": overall, "summary": summary, "week_ranges": week_ranges, "findings": findings}


# ---------------------------------------------------------------------------
# Week-over-week driver analysis (newest displayed week vs. prior displayed week)
# ---------------------------------------------------------------------------
def split_contributors(ranked_df, metric):
    """Split a contribution.rank_contributors() result into detractors
    (moved the additive metric down) and offsetting positives (moved it
    up), each sorted by size of impact."""
    col = f"{metric}_abs_change"
    detractors = ranked_df[ranked_df[col] < 0].sort_values(col)
    offsets = ranked_df[ranked_df[col] > 0].sort_values(col, ascending=False)
    return detractors, offsets


def split_rate_movers(rate_df, metric, materiality=MATERIALITY):
    """Split a contribution.rate_changes() result into deteriorating vs.
    improving campaigns for a ratio metric, honoring METRIC_DIRECTION
    (a CPA increase deteriorates; a conversion-rate increase improves).
    Only moves at least `materiality` in size are included."""
    col = f"{metric}_pct_change"
    direction = METRIC_DIRECTION.get(metric, "higher_is_better")
    meaningful = rate_df[rate_df[col].abs() >= materiality]
    if direction == "lower_is_better":
        deteriorating = meaningful[meaningful[col] > 0].sort_values(col, ascending=False)
        improving = meaningful[meaningful[col] < 0].sort_values(col)
    else:
        deteriorating = meaningful[meaningful[col] < 0].sort_values(col)
        improving = meaningful[meaningful[col] > 0].sort_values(col, ascending=False)
    return deteriorating, improving
