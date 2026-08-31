"""
Change intelligence: correlate the account change log with performance
shifts.

This module is deliberately conservative about language. It can tell you
that a change happened shortly before a metric moved ("occurred before"),
but it never claims the change caused the shift unless the investigation
engine has separately gathered corroborating evidence (see
investigation.py). Timing alone is a clue, not proof.
"""

from datetime import timedelta

from src.metrics import aggregate
from src.formatting import fmt_or_dash


def changes_for_campaign(changes_df, campaign):
    return changes_df[changes_df["campaign"] == campaign].sort_values("date")


def changes_before_date(changes_df, campaign, reference_date, lookback_days=5):
    """Changes to `campaign` in the `lookback_days` before (and including)
    reference_date. Used to ask 'what happened right before this shift?'"""
    window_start = reference_date - timedelta(days=lookback_days)
    subset = changes_for_campaign(changes_df, campaign)
    return subset[(subset["date"] >= window_start) & (subset["date"] <= reference_date)]


def describe_changes(changes_subset):
    """Turn a DataFrame of change rows into plain-English bullet strings.
    Missing old/new values (e.g. a brand-new setting with no prior value)
    render as "not set", never a raw "nan" -- a bare f-string would print
    "nan" here since an empty CSV field loads as a NaN float, and NaN
    doesn't get caught by a plain `value or default` check (NaN is
    truthy in Python)."""
    lines = []
    for _, row in changes_subset.iterrows():
        old_value = fmt_or_dash(row["old_value"], empty_meaning="not set")
        new_value = fmt_or_dash(row["new_value"], empty_meaning="not set")
        lines.append(
            f"{row['date']}: {row['entity']} — {row['change_type'].replace('_', ' ')} "
            f"(\"{old_value}\" -> \"{new_value}\"), by {row['changed_by']}. {row['notes']}"
        )
    return lines


def performance_around_change(campaigns_df, campaign, change_date, window_days=7):
    """Aggregate campaign performance in the `window_days` immediately
    before vs. immediately after a change date, so a change-log entry can
    be shown alongside what happened around it. This is descriptive only
    -- it reports a before/after difference, never a causal claim. Use
    src/investigation.py or src/evidence.py if a hypothesis with
    corroborating evidence (auction data, other campaigns unaffected) is
    needed to say anything stronger than "performance changed shortly
    after this."""
    subset = campaigns_df[campaigns_df["campaign"] == campaign]
    before = subset[(subset["date"] >= change_date - timedelta(days=window_days)) & (subset["date"] < change_date)]
    after = subset[(subset["date"] > change_date) & (subset["date"] <= change_date + timedelta(days=window_days))]

    before_agg = aggregate(before, group_by=None)
    after_agg = aggregate(after, group_by=None)
    has_data = not before_agg.empty and not after_agg.empty and len(before) > 0 and len(after) > 0

    return {
        "has_data": has_data,
        "before": before_agg.iloc[0].to_dict() if not before_agg.empty else {},
        "after": after_agg.iloc[0].to_dict() if not after_agg.empty else {},
        "window_days": window_days,
    }
