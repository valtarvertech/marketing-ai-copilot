"""
Deterministic metric calculations.

This module is the one place that knows how to turn raw advertising
numbers (impressions, clicks, spend, conversions, conversion value) into
the standard performance ratios (CTR, CPC, conversion rate, CPA, ROAS).
Everything here is plain arithmetic -- no AI, no external calls -- so the
numbers the rest of the app relies on are always exact and reproducible.

Important rule followed throughout this codebase: when aggregating
multiple rows (e.g. a week of data, or every campaign in an account),
we always sum the raw numbers first and THEN divide, rather than
averaging each day's ratio. Averaging ratios directly is a common
analytics mistake -- it weights a low-volume day the same as a
high-volume day, which distorts the real blended rate.
"""

import numpy as np
import pandas as pd

RAW_METRICS = ["impressions", "clicks", "spend", "conversions", "conversion_value"]
DERIVED_METRICS = ["ctr", "cpc", "conversion_rate", "cpa", "roas"]
ALL_METRICS = RAW_METRICS + DERIVED_METRICS

# Whether a rise in this metric is good, bad, or context-dependent news.
# This is what "favorable" means throughout the UI -- e.g. a CPA increase
# is unfavorable even though the number went up, which naive
# up-is-green treatments get wrong.
METRIC_DIRECTION = {
    "conversions": "higher_is_better",
    "roas": "higher_is_better",
    "conversion_rate": "higher_is_better",
    "ctr": "higher_is_better",  # favorable, but a lower-priority signal than business outcomes
    "cpa": "lower_is_better",
    "cpc": "lower_is_better",
    "spend": "neutral",
    "impressions": "neutral",
    "conversion_value": "neutral",
    "clicks": "neutral",
}


def favorability(metric, pct_change, materiality=0.05):
    """Classify a percent change as "Favorable", "Unfavorable", "Flat", or
    "Neutral", accounting for whether higher or lower is better for this
    particular metric (see METRIC_DIRECTION). Returns "No data" if
    pct_change is missing."""
    direction = METRIC_DIRECTION.get(metric, "neutral")
    if direction == "neutral":
        return "Neutral"
    if pct_change is None or (isinstance(pct_change, float) and np.isnan(pct_change)):
        return "No data"
    if abs(pct_change) < materiality:
        return "Flat"
    if direction == "higher_is_better":
        return "Favorable" if pct_change > 0 else "Unfavorable"
    return "Favorable" if pct_change < 0 else "Unfavorable"


def safe_div(numerator, denominator, default=0.0):
    """Divide, returning `default` instead of raising/NaN/inf on a zero
    denominator. Works for plain numbers and for pandas/numpy Series."""
    if isinstance(denominator, (pd.Series, np.ndarray)):
        denominator = pd.Series(denominator)
        numerator = pd.Series(numerator)
        with np.errstate(divide="ignore", invalid="ignore"):
            result = numerator / denominator.replace(0, np.nan)
        return result.fillna(default)
    return numerator / denominator if denominator else default


def add_derived_metrics(df):
    """Return a copy of df with CTR/CPC/conversion_rate/CPA/ROAS columns
    added, computed row by row from the raw columns already present."""
    out = df.copy()
    out["ctr"] = safe_div(out["clicks"], out["impressions"])
    out["cpc"] = safe_div(out["spend"], out["clicks"])
    out["conversion_rate"] = safe_div(out["conversions"], out["clicks"])
    out["cpa"] = safe_div(out["spend"], out["conversions"])
    out["roas"] = safe_div(out["conversion_value"], out["spend"])
    return out


def aggregate(df, group_by=None):
    """Sum the raw metrics (optionally grouped by one or more columns,
    e.g. "campaign") and derive CTR/CPC/conversion_rate/CPA/ROAS from
    those sums. Returns a DataFrame; pass group_by=None to get a single
    account-level total row.
    """
    if group_by:
        grouped = df.groupby(group_by, as_index=False)[RAW_METRICS].sum()
    else:
        grouped = pd.DataFrame([df[RAW_METRICS].sum()])

    return add_derived_metrics(grouped)
