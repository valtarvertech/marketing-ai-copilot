"""
Contribution analysis: when an account-level number changes, which
campaigns actually drove that change?

This only works cleanly for the additive raw metrics (impressions,
clicks, spend, conversions, conversion_value) -- their per-campaign
changes sum to the account-level change, so we can express each
campaign's "contribution share" as its slice of the total move.

Rate metrics (CTR, CPC, conversion rate, CPA, ROAS) are NOT additive
across campaigns -- you can't sum two conversion rates and get a
meaningful account-level rate. For those we report each campaign's own
before/after rate change as supporting evidence instead of a
"contribution share".
"""

from src.comparisons import filter_date_range, compare
from src.metrics import RAW_METRICS, DERIVED_METRICS, safe_div


def rank_contributors(df, metric, current_range, previous_range, group_by="campaign"):
    """Rank campaigns (or another group_by column) by how much of the
    account-level change in `metric` they're responsible for.

    `metric` must be one of RAW_METRICS. Returns (ranked_df, total_change).
    ranked_df is sorted by the size of the contribution, largest first,
    and includes a `contribution_share` column (fraction of the total
    account-level change; can be negative if a campaign moved opposite
    the overall trend).
    """
    if metric not in RAW_METRICS:
        raise ValueError(
            f"rank_contributors only supports additive metrics {RAW_METRICS}; "
            f"got '{metric}'. Use rate_changes() for CTR/CPC/conversion_rate/CPA/ROAS."
        )

    current_df = filter_date_range(df, *current_range)
    previous_df = filter_date_range(df, *previous_range)

    by_group = compare(current_df, previous_df, group_by=group_by)
    total = compare(current_df, previous_df, group_by=None)

    total_change = total[f"{metric}_abs_change"].iloc[0]
    by_group["contribution_share"] = safe_div(by_group[f"{metric}_abs_change"], total_change, default=0.0)

    cols = [group_by, f"{metric}_current", f"{metric}_previous", f"{metric}_abs_change",
            f"{metric}_pct_change", "contribution_share"]
    ranked = by_group[cols].copy()
    ranked = ranked.reindex(ranked[f"{metric}_abs_change"].abs().sort_values(ascending=False).index)
    return ranked.reset_index(drop=True), total_change


def rate_changes(df, metric, current_range, previous_range, group_by="campaign"):
    """Return each group's own before/after value for a rate metric
    (CTR, CPC, conversion_rate, CPA, ROAS), sorted by size of change.
    This is evidence to inspect, not a "contribution to the total"."""
    if metric not in DERIVED_METRICS:
        raise ValueError(f"rate_changes expects one of {DERIVED_METRICS}; got '{metric}'.")

    current_df = filter_date_range(df, *current_range)
    previous_df = filter_date_range(df, *previous_range)
    by_group = compare(current_df, previous_df, group_by=group_by)

    cols = [group_by, f"{metric}_current", f"{metric}_previous", f"{metric}_abs_change", f"{metric}_pct_change"]
    ranked = by_group[cols].copy()
    ranked = ranked.reindex(ranked[f"{metric}_abs_change"].abs().sort_values(ascending=False).index)
    return ranked.reset_index(drop=True)
