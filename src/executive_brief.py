"""
Executive Overview "Performance Brief" -- a short, deterministic,
rule-based narrative summarizing the last 7 days vs. the prior 7 days.

This is NOT an AI-generated summary. It reuses the same comparison and
contribution functions as the rest of the app (src/comparisons.py,
src/contribution.py) and the same favorable/unfavorable classification
used on the Executive Overview KPI cards (src/metrics.favorability), so
the narrative can never disagree with the numbers shown next to it.
"""

import pandas as pd

from src.comparisons import compare, filter_date_range, week_over_week_range
from src.contribution import rank_contributors, rate_changes
from src.metrics import RAW_METRICS, METRIC_DIRECTION
from src.rolling import format_date_range

# A metric must move at least this much (account-wide, week over week) to
# be worth mentioning in the brief -- keeps small noise out of the narrative.
MATERIALITY = 0.05

# Business-outcome metrics take priority over CTR, which is a lower-priority
# signal (see METRIC_DIRECTION / the KPI directionality spec).
PRIMARY_METRICS = ["conversions", "roas", "conversion_rate", "cpa", "cpc"]
SECONDARY_METRICS = ["ctr"]

METRIC_LABELS = {
    "conversions": "conversions", "roas": "ROAS", "conversion_rate": "conversion rate",
    "cpa": "CPA", "cpc": "CPC", "ctr": "CTR",
}


def _signed_impact(metric, pct_change):
    """Positive = favorable movement, negative = unfavorable, magnitude
    reflects size -- regardless of whether raw pct_change was positive or
    negative (a CPA drop is a positive impact)."""
    if pct_change is None or pd.isna(pct_change):
        return 0.0
    direction = METRIC_DIRECTION.get(metric, "neutral")
    if direction == "higher_is_better":
        return pct_change
    if direction == "lower_is_better":
        return -pct_change
    return 0.0


def _top_campaigns_for_metric(campaigns_df, metric, current_range, previous_range, top_n=2, threshold=0.08):
    if metric in RAW_METRICS:
        ranked, _ = rank_contributors(campaigns_df, metric, current_range, previous_range)
    else:
        ranked = rate_changes(campaigns_df, metric, current_range, previous_range)

    pct_col = f"{metric}_pct_change"
    notable = ranked[ranked[pct_col].abs() >= threshold]
    return notable["campaign"].head(top_n).tolist()


def _describe(campaigns_df, metric, pct_change, current_range, previous_range):
    label = METRIC_LABELS.get(metric, metric)
    direction_word = "up" if pct_change > 0 else "down"
    campaigns = _top_campaigns_for_metric(campaigns_df, metric, current_range, previous_range, top_n=1)
    text = f"{label} {direction_word} {abs(pct_change):.0%}"
    if campaigns:
        text += f', concentrated in "{campaigns[0]}"'
    return text


def generate_brief(campaigns_df, current_range=None, previous_range=None):
    """Return a dict describing what changed, the overall direction, the
    top issue, the top positive signal, and which campaign(s) are worth
    investigating -- plus a ready-to-display `summary` string (2-4
    sentences).

    Defaults to week-over-week if no explicit ranges are given. Pass
    src.rolling.rolling_8_day_range()'s (current_start, current_end,
    previous_start, previous_end) (split into two 2-tuples) to generate
    the same kind of brief over the Executive Overview's rolling 8-day
    period instead -- the underlying logic (materiality, directionality,
    contribution) is identical either way."""
    if current_range is None or previous_range is None:
        current_range = week_over_week_range(campaigns_df)[0:2]
        previous_range = week_over_week_range(campaigns_df)[2:4]

    period_label = format_date_range(*current_range)
    account = compare(
        filter_date_range(campaigns_df, *current_range), filter_date_range(campaigns_df, *previous_range),
        group_by=None,
    ).iloc[0]

    candidates = []
    for metric in PRIMARY_METRICS + SECONDARY_METRICS:
        pct = account[f"{metric}_pct_change"]
        if pct is None or pd.isna(pct) or abs(pct) < MATERIALITY:
            continue
        candidates.append((metric, pct, _signed_impact(metric, pct)))

    primary_candidates = [c for c in candidates if c[0] in PRIMARY_METRICS]
    pool = primary_candidates if primary_candidates else candidates

    # Partition by sign first, then take the extreme of each side. Picking
    # min()/max() of the whole pool before filtering by sign would wrongly
    # null out the only signal when just one candidate exists (min and max
    # of a 1-item list are the same item, tripping the same-metric check).
    unfavorable = [c for c in pool if c[2] < 0]
    favorable = [c for c in pool if c[2] > 0]
    worst = min(unfavorable, key=lambda c: c[2]) if unfavorable else None
    best = max(favorable, key=lambda c: c[2]) if favorable else None

    investigate_campaigns = []
    if worst is not None:
        investigate_campaigns = _top_campaigns_for_metric(campaigns_df, worst[0], current_range, previous_range)

    if worst is None and best is None:
        overall = "Stable"
        summary = f"Performance remained stable during {period_label} versus the prior equivalent period."
    else:
        sentence_parts = []
        if worst is not None:
            sentence_parts.append(f"the most pressing issue is {_describe(campaigns_df, *worst[:2], current_range, previous_range)}")
        if best is not None:
            sentence_parts.append(f"the strongest positive signal is {_describe(campaigns_df, *best[:2], current_range, previous_range)}")

        overall = "Mixed" if (worst is not None and best is not None) else ("Unfavorable" if worst is not None else "Favorable")
        summary = f"Performance was {overall.lower()} during {period_label}: " + "; ".join(sentence_parts) + "."
        if investigate_campaigns:
            summary += f" Recommend investigating: {', '.join(investigate_campaigns)}."

    return {
        "overall": overall,
        "summary": summary,
        "worst_metric": worst[0] if worst else None,
        "best_metric": best[0] if best else None,
        "investigate_campaigns": investigate_campaigns,
    }
