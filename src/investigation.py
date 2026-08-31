"""
The investigation engine -- the core differentiator of Marketing AI
Copilot.

Given a question like "why did conversions decrease?", this module does
NOT jump straight to an answer. It works through an explicit,
evidence-based sequence, and every stage of that sequence is kept in the
returned report so the UI can show its work:

    1. VERIFY      - did the metric actually change?
    2. QUANTIFY     - by how much (absolute + percent)?
    3. LOCALIZE     - which campaigns drove the account-level change?
    4. INVESTIGATE  - for the top contributors, walk the performance
                      chain (impressions -> clicks -> CTR -> CPC ->
                      conversion rate) plus change history and
                      auction/competitive signals.
    5. HYPOTHESIZE  - propose a likely driver per contributor, using
                      simple, transparent rules (never a black box).
    6. TEST         - check the hypothesis against corroborating
                      evidence (change log timing, auction trends) and
                      adjust confidence accordingly.
    7. CONCLUDE     - a plain-English, hedged conclusion.
    8. RECOMMEND    - handed off to src/recommendations.py.

Everything here is rule-based arithmetic and comparisons -- no AI model
is involved in deciding what happened. An AI layer (src/ai_layer.py)
can later turn this structured report into more natural prose, but it
receives these facts, it does not invent them.

Confidence is always "High" / "Medium" / "Low" based on transparent
rules -- never a fabricated statistic like "93.7% confidence".
"""

from src.comparisons import day_over_day_range, week_over_week_range, filter_date_range, compare
from src.contribution import rank_contributors, rate_changes
from src.change_intelligence import changes_before_date, describe_changes
from src.competitive import auction_trend, summarize_competitive_pressure
from src.metrics import RAW_METRICS
from src.formatting import metric_label, metric_phrase

MEANINGFUL_MOVE = 0.10  # a relative change bigger than this is "meaningful"
FLAT_MOVE = 0.07        # a relative change smaller than this counts as "roughly flat"
MATERIAL_ACCOUNT_CHANGE = 0.05  # ignore account-level noise below this


def _period_ranges(df, period):
    if period == "day_over_day":
        cur_start, cur_end, prev_start, prev_end = day_over_day_range(df)
    elif period == "week_over_week":
        cur_start, cur_end, prev_start, prev_end = week_over_week_range(df)
    else:
        raise ValueError("period must be 'day_over_day' or 'week_over_week'")
    return (cur_start, cur_end), (prev_start, prev_end)


def _verify_and_quantify(df, metric, current_range, previous_range):
    current_df = filter_date_range(df, *current_range)
    previous_df = filter_date_range(df, *previous_range)
    total = compare(current_df, previous_df, group_by=None)

    current_value = total[f"{metric}_current"].iloc[0]
    previous_value = total[f"{metric}_previous"].iloc[0]
    abs_change = total[f"{metric}_abs_change"].iloc[0]
    pct_change = total[f"{metric}_pct_change"].iloc[0]

    changed = pct_change is not None and abs(pct_change) >= MATERIAL_ACCOUNT_CHANGE
    direction = "increased" if abs_change > 0 else ("decreased" if abs_change < 0 else "did not change")

    return {
        "metric": metric,
        "current_value": current_value,
        "previous_value": previous_value,
        "abs_change": abs_change,
        "pct_change": pct_change,
        "changed_materially": changed,
        "direction": direction,
    }


def _classify_driver(rate_evidence, volume_evidence):
    clicks_pct = volume_evidence.get("clicks_pct_change")
    impressions_pct = volume_evidence.get("impressions_pct_change")
    cvr_pct = rate_evidence.get("conversion_rate_pct_change")
    cpc_pct = rate_evidence.get("cpc_pct_change")
    ctr_pct = rate_evidence.get("ctr_pct_change")

    def flat(x):
        return x is not None and abs(x) <= FLAT_MOVE

    def meaningful(x, direction=None):
        if x is None:
            return False
        if direction == "up":
            return x >= MEANINGFUL_MOVE
        if direction == "down":
            return x <= -MEANINGFUL_MOVE
        return abs(x) >= MEANINGFUL_MOVE

    if meaningful(clicks_pct, "up") and meaningful(cvr_pct, "down"):
        return {
            "driver": "possible_search_term_waste",
            "text": "Clicks rose but conversion rate fell at the same time -- new traffic is arriving that "
                    "converts worse than the existing traffic. Worth checking the search-term report for "
                    "low-quality queries consuming spend without converting.",
            "confidence": "Medium",
        }

    if flat(clicks_pct) and meaningful(cvr_pct, "down"):
        confidence = "High" if cvr_pct <= -0.20 else "Medium"
        return {
            "driver": "conversion_rate_decline",
            "text": "Traffic (clicks) is roughly flat, but conversion rate dropped meaningfully -- "
                    "this looks like a funnel/efficiency problem after the click, not a traffic problem.",
            "confidence": confidence,
        }

    if flat(clicks_pct) and meaningful(cvr_pct, "up"):
        return {
            "driver": "conversion_rate_improvement",
            "text": "Traffic (clicks) is roughly flat, but conversion rate improved meaningfully -- "
                    "something in the funnel after the click got better (e.g. a landing page, offer, "
                    "or targeting/search-term quality change).",
            "confidence": "High" if cvr_pct >= 0.15 else "Medium",
        }

    if meaningful(clicks_pct, "down") and flat(ctr_pct) and flat(cpc_pct):
        return {
            "driver": "volume_decline",
            "text": "Clicks fell while CTR and CPC stayed stable -- this points to fewer people being "
                    "reached (demand, budget, or impression-share issue), not worse ad performance.",
            "confidence": "Medium",
        }

    if meaningful(cpc_pct, "up") and flat(clicks_pct):
        return {
            "driver": "cpc_pressure",
            "text": "Cost per click rose while traffic held steady -- consistent with increased "
                    "competitive/auction pressure rather than a change this account made.",
            "confidence": "Medium",
        }

    if meaningful(impressions_pct, "down") and flat(ctr_pct):
        return {
            "driver": "reach_decline",
            "text": "Impressions fell with CTR unaffected -- fewer people are seeing the ads at all.",
            "confidence": "Low",
        }

    return {
        "driver": "unclear",
        "text": "No single dominant driver stood out from CTR/CPC/conversion-rate movement alone.",
        "confidence": "Low",
    }


def investigate_metric_change(campaigns_df, changes_df, auction_df, metric="conversions",
                               period="week_over_week", campaign=None):
    """Run the investigation using one of the two standard rolling
    windows (day_over_day or week_over_week), relative to the most
    recent date in the dataset. See investigate_range() for investigating
    an arbitrary, explicit pair of date ranges (e.g. to look at a period
    further back in history). Pass `campaign` to scope the whole
    investigation to a single campaign instead of the account."""
    current_range, previous_range = _period_ranges(campaigns_df, period)
    return investigate_range(campaigns_df, changes_df, auction_df, metric, current_range, previous_range,
                              campaign=campaign)


def investigate_range(campaigns_df, changes_df, auction_df, metric, current_range, previous_range, campaign=None):
    """Run the full VERIFY -> QUANTIFY -> LOCALIZE -> INVESTIGATE ->
    HYPOTHESIZE -> TEST -> CONCLUDE sequence for one metric over an
    explicit pair of (start, end) date ranges. Returns a dict with one
    key per stage, ready for both the CLI/README style summary and the
    Streamlit evidence panels.

    `metric` should normally be one of RAW_METRICS (conversions, clicks,
    spend, impressions, conversion_value) so contribution analysis is
    meaningful; rate metrics can be investigated but skip the
    contribution-share step in favor of raw rate comparison.

    By default this investigates the whole account. Pass `campaign` (a
    campaign name) to scope every stage to just that campaign -- useful
    when a localized issue is too small to move the account-level
    number past the "materially changed" threshold, or when the user is
    specifically asking about one campaign.
    """
    scoped_df = campaigns_df[campaigns_df["campaign"] == campaign] if campaign else campaigns_df

    verify = _verify_and_quantify(scoped_df, metric, current_range, previous_range)

    localize = {"is_additive_metric": metric in RAW_METRICS, "scoped_to_campaign": campaign}
    if campaign:
        top_campaigns = [campaign]
        if metric in RAW_METRICS:
            ranked, total_change = rank_contributors(campaigns_df, metric, current_range, previous_range)
            localize["ranked_contributors"] = ranked[ranked["campaign"] == campaign].reset_index(drop=True)
            localize["total_change"] = total_change
        else:
            ranked = rate_changes(campaigns_df, metric, current_range, previous_range)
            localize["ranked_contributors"] = ranked[ranked["campaign"] == campaign].reset_index(drop=True)
    elif metric in RAW_METRICS:
        ranked, total_change = rank_contributors(campaigns_df, metric, current_range, previous_range)
        localize["ranked_contributors"] = ranked
        localize["total_change"] = total_change
        top_campaigns = ranked["campaign"].head(3).tolist()
    else:
        ranked = rate_changes(campaigns_df, metric, current_range, previous_range)
        localize["ranked_contributors"] = ranked
        top_campaigns = ranked["campaign"].head(3).tolist()

    investigate = {}
    hypotheses = {}
    for campaign in top_campaigns:
        rate_table = {}
        for rate_metric in ["ctr", "cpc", "conversion_rate", "cpa", "roas"]:
            rc = rate_changes(campaigns_df, rate_metric, current_range, previous_range)
            row = rc[rc["campaign"] == campaign]
            if not row.empty:
                rate_table[f"{rate_metric}_pct_change"] = row.iloc[0][f"{rate_metric}_pct_change"]

        volume_table = {}
        for raw_metric in ["impressions", "clicks"]:
            vol_ranked, _ = rank_contributors(campaigns_df, raw_metric, current_range, previous_range)
            row = vol_ranked[vol_ranked["campaign"] == campaign]
            if not row.empty:
                volume_table[f"{raw_metric}_pct_change"] = row.iloc[0][f"{raw_metric}_pct_change"]

        recent_changes = changes_before_date(changes_df, campaign, current_range[0], lookback_days=5)
        change_lines = describe_changes(recent_changes)

        trend = auction_trend(auction_df, campaign, current_range, previous_range)
        auction_lines = summarize_competitive_pressure(trend)

        investigate[campaign] = {
            "rate_evidence": rate_table,
            "volume_evidence": volume_table,
            "recent_changes": change_lines,
            "auction_evidence": auction_lines,
        }

        hypothesis = _classify_driver(rate_table, volume_table)

        # TEST: corroborate the hypothesis with change-log timing and
        # auction evidence. A hypothesis that already has direct
        # supporting evidence gets bumped in confidence; a hypothesis
        # with a merely-coincidental nearby change stays hedged as
        # correlation, not causation.
        if hypothesis["driver"] == "cpc_pressure" and any("outranking" in line.lower() or "rank" in line.lower() for line in auction_lines):
            hypothesis["confidence"] = "High"
            hypothesis["text"] += " Auction data corroborates this: " + auction_lines[0]
        if hypothesis["driver"] == "volume_decline" and any("budget" in line.lower() for line in auction_lines):
            hypothesis["driver"] = "volume_decline_budget_constrained"
            hypothesis["confidence"] = "High"
            hypothesis["text"] += " Auction data corroborates this: " + next(
                (l for l in auction_lines if "budget" in l.lower()), ""
            )
        if change_lines:
            hypothesis["correlated_changes"] = change_lines
            hypothesis["text"] += (
                f" Note: {len(change_lines)} account change(s) occurred in the days before this shift for "
                f"{campaign} -- listed as evidence below. Timing alone does not prove they caused this change."
            )

        hypotheses[campaign] = hypothesis

    conclusion = _build_conclusion(verify, metric, top_campaigns, hypotheses)

    return {
        "metric": metric,
        "current_range": current_range,
        "previous_range": previous_range,
        "verify": verify,
        "localize": localize,
        "investigate": investigate,
        "hypotheses": hypotheses,
        "conclusion": conclusion,
    }


def _build_conclusion(verify, metric, top_campaigns, hypotheses):
    label = metric_label(metric)

    if not verify["changed_materially"]:
        if verify["pct_change"] is not None:
            direction_word = "increased" if verify["pct_change"] > 0 else "decreased"
            return (
                f"{label} {direction_word} {abs(verify['pct_change']):.1%}, below the "
                f"{MATERIAL_ACCOUNT_CHANGE:.0%} materiality threshold. No investigation is currently warranted."
            )
        return f"{label} is effectively unchanged. No investigation is currently warranted."

    phrase = metric_phrase(metric)
    if verify["pct_change"] is not None:
        lines = [
            f"Account-level {phrase} {verify['direction']} by {abs(verify['abs_change']):,.1f} "
            f"({verify['pct_change']:+.1%})."
        ]
    else:
        lines = [f"Account-level {phrase} {verify['direction']} by {abs(verify['abs_change']):,.1f}."]

    for campaign in top_campaigns:
        h = hypotheses.get(campaign, {})
        if h:
            lines.append(f'"{campaign}": {h.get("text", "")} (confidence: {h.get("confidence", "Low")})')

    return " ".join(lines)
