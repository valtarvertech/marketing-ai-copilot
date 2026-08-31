"""
Single source of truth for how numbers are displayed anywhere in the app.

Every page formats impressions, spend, CTR, ROAS, etc. through these
functions instead of ad-hoc f-strings, so a percentage never shows as a
raw decimal (0.0368) and a currency value never gets truncated mid-number.
"""

import pandas as pd

RAW_METRIC_LABELS = {
    "impressions": "Impressions", "clicks": "Clicks", "spend": "Spend",
    "conversions": "Conversions", "conversion_value": "Conversion Value",
}
RATE_METRIC_LABELS = {
    "ctr": "CTR", "cpc": "CPC", "conversion_rate": "Conversion Rate",
    "cpa": "CPA", "roas": "ROAS",
}
ALL_METRIC_LABELS = {**RAW_METRIC_LABELS, **RATE_METRIC_LABELS}


def fmt_count(v):
    return "n/a" if v is None or pd.isna(v) else f"{v:,.0f}"


def fmt_money(v):
    return "n/a" if v is None or pd.isna(v) else f"${v:,.2f}"


def fmt_percent(v, signed=False):
    if v is None or pd.isna(v):
        return "n/a"
    return f"{v:+.1%}" if signed else f"{v:.1%}"


def fmt_ratio_x(v):
    return "n/a" if v is None or pd.isna(v) else f"{v:.2f}x"


def fmt_points(v, signed=True):
    """Percentage-point delta, e.g. impression share moving from 55% to
    49% is '-6.0 pts', not a percent-of-a-percent."""
    if v is None or pd.isna(v):
        return "n/a"
    pts = v * 100
    return f"{pts:+.1f} pts" if signed else f"{pts:.1f} pts"


# One formatter per underlying metric key -- the thing that guarantees
# CTR/Conversion Rate never render as a bare decimal and Spend/CPA/CPC
# never render unformatted.
METRIC_FORMATTERS = {
    "impressions": fmt_count, "clicks": fmt_count, "conversions": fmt_count,
    "spend": fmt_money, "conversion_value": fmt_money, "cpc": fmt_money, "cpa": fmt_money,
    "ctr": fmt_percent, "conversion_rate": fmt_percent,
    "roas": fmt_ratio_x,
}


def format_metric(metric, value):
    return METRIC_FORMATTERS.get(metric, lambda v: f"{v:,.2f}")(value)


def metric_label(metric):
    """Human label for a metric key, with correct acronym casing (CPA,
    CTR, CPC, ROAS) -- plain str.title() turns "cpa" into "Cpa", not
    "CPA", which is why this table exists rather than a mechanical
    string transform."""
    return ALL_METRIC_LABELS.get(metric, metric.replace("_", " ").title())


def metric_phrase(metric):
    """Lowercased metric label for embedding mid-sentence ("conversions
    decreased", "spend rose") -- except acronyms (CPA, CPC, CTR, ROAS)
    stay uppercase, since lowercasing those reads as a typo, not prose."""
    label = metric_label(metric)
    return label if label.isupper() else label.lower()


def fmt_or_dash(value, empty_meaning="Not set"):
    """Render a possibly-missing value (None, NaN, or an empty string --
    all of which pandas can produce for a genuinely-absent field, e.g. a
    change log entry for a brand-new setting with no prior value) as a
    clear em dash with a title explaining what's missing, instead of the
    raw "nan"/"None" a naive f-string would produce."""
    if value is None or (isinstance(value, float) and pd.isna(value)) or (isinstance(value, str) and not value.strip()):
        return f"— ({empty_meaning})"
    return str(value)


def chronological_categories(labels):
    """Wrap a list of display labels (already in the correct chronological
    order) as an ordered pandas Categorical, so Streamlit/Vega-Lite charts
    treat the axis as ordinal-with-explicit-sort instead of nominal --
    which defaults to *alphabetical* sort and silently scrambles labels
    like "Aug 3-9" / "Aug 24-30" / "Jul 27-Aug 2" out of time order."""
    labels = list(labels)
    return pd.Categorical(labels, categories=labels, ordered=True)
