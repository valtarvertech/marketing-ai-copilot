"""
Cross-module evidence service.

Individual modules (metrics, comparisons, contribution, investigation,
pacing, competitive, change_intelligence, search_term_intelligence) each
answer one narrow question well. This module composes their outputs so
that:

  - Optimization Center can write a recommendation that weighs pacing,
    performance, and competitive signals together, instead of each
    module generating recommendations in isolation.
  - Ask My Account can answer "why did conversions decrease?" by
    walking the same multi-step chain a human analyst would (traffic ->
    conversion rate -> search-term quality -> budget -> competitive ->
    recent changes), not by returning a single number.
  - Campaign Intelligence's evidence trail can show alternative
    explanations and a suggested next test, not just the single
    winning hypothesis.

Everything here is still deterministic arithmetic and rule-based
synthesis. This is the layer a future AI explainer (src/ai_layer.py)
would sit on top of: an LLM would receive this structured evidence and
write prose about it, never recompute the underlying numbers.
"""

from src.metrics import aggregate, METRIC_DIRECTION
from src.investigation import investigate_range
from src.search_term_intelligence import waste_share
from src.pacing import compute_pacing, STATUS_OVER, STATUS_UNDER, STATUS_ON_TRACK

# --- Suggested next test, by hypothesis driver -----------------------------
NEXT_TEST_BY_DRIVER = {
    "conversion_rate_decline": "Compare pre/post conversion performance around any recent landing "
                                "page, offer, or targeting change, and segment conversion rate by "
                                "device to isolate where the drop is concentrated.",
    "conversion_rate_improvement": "Confirm the improvement holds for another full week before "
                                    "reallocating budget toward this campaign.",
    "volume_decline": "Check impression share and ad scheduling/targeting settings to determine "
                       "whether reduced reach is demand-side or self-imposed.",
    "volume_decline_budget_constrained": "Evaluate whether current ROAS/CPA justifies a budget "
                                          "increase before raising spend -- see Budget Pacing.",
    "cpc_pressure": "Review auction insights for the specific competitor gaining share; consider "
                     "bid strategy and ad rank adjustments rather than an across-the-board bid cut.",
    "possible_search_term_waste": "Pull the search-term report for this campaign and period and "
                                   "review candidates for negative keywords -- see Search Term Intelligence.",
    "reach_decline": "Check impression share trends and recent targeting/scheduling changes for "
                      "unintended restriction.",
    "unclear": "No single dominant driver was identified from the signals checked; monitor for "
               "another period before acting.",
}


def account_benchmark(campaigns_df, start_date, end_date):
    """Account-level blended rates for a period -- the reference point for
    "is this campaign relatively strong or weak?" rather than an
    arbitrary fixed threshold."""
    subset = campaigns_df[(campaigns_df["date"] >= start_date) & (campaigns_df["date"] <= end_date)]
    agg = aggregate(subset, group_by=None)
    if agg.empty:
        return {"roas": 0.0, "cpa": 0.0, "conversion_rate": 0.0}
    row = agg.iloc[0]
    return {"roas": row["roas"], "cpa": row["cpa"], "conversion_rate": row["conversion_rate"]}


# --- Pacing + performance context -------------------------------------------
CONTEXT_OPPORTUNITY = "Opportunity"
CONTEXT_CAUTION = "Caution"
CONTEXT_REVIEW = "Review"
CONTEXT_AT_RISK = "At Risk"
CONTEXT_MONITOR = "Monitor"
CONTEXT_ON_TRACK = "On Track"


def campaign_pacing_context(pacing_status, campaign_roas, account_roas):
    """Combine a campaign's pacing status with how its efficiency compares
    to the account's own blended average -- NOT a fixed ROAS floor -- to
    decide whether under-pacing is really an opportunity to scale, or a
    reason for caution. Under-pacing alone never implies "spend more";
    over-pacing alone never implies "cut spend" -- performance decides.
    """
    stronger_than_account = campaign_roas >= account_roas

    if pacing_status == STATUS_UNDER:
        if stronger_than_account:
            return CONTEXT_OPPORTUNITY, (
                f"Under-pacing with ROAS ({campaign_roas:.2f}x) at or above the account average "
                f"({account_roas:.2f}x) -- a reasonable candidate to evaluate for additional budget."
            )
        return CONTEXT_CAUTION, (
            f"Under-pacing, but ROAS ({campaign_roas:.2f}x) is below the account average "
            f"({account_roas:.2f}x). Increasing spend here is not automatically appropriate -- "
            f"investigate efficiency before scaling."
        )

    if pacing_status == STATUS_OVER:
        if stronger_than_account:
            return CONTEXT_REVIEW, (
                f"Over-pacing, but ROAS ({campaign_roas:.2f}x) remains at or above the account "
                f"average ({account_roas:.2f}x) -- a budget increase may be warranted rather than "
                f"throttling a campaign that is performing well."
            )
        return CONTEXT_AT_RISK, (
            f"Over-pacing while ROAS ({campaign_roas:.2f}x) is below the account average "
            f"({account_roas:.2f}x) -- a high-priority efficiency issue: this campaign is "
            f"consuming budget faster than average while returning less than average."
        )

    # On pace
    if stronger_than_account:
        return CONTEXT_ON_TRACK, f"On pace with ROAS ({campaign_roas:.2f}x) at or above the account average."
    return CONTEXT_MONITOR, (
        f"On pace, but ROAS ({campaign_roas:.2f}x) is below the account average "
        f"({account_roas:.2f}x) -- pacing itself isn't the issue, efficiency is worth monitoring."
    )


def build_pacing_contexts(campaigns_df, as_of_date):
    """Pacing status + performance-aware context for every campaign, as of
    as_of_date. Used by Budget Pacing and Optimization Center."""
    pacing_df = compute_pacing(campaigns_df, as_of_date, group_by="campaign")
    bench_start = as_of_date.replace(day=1)
    bench = account_benchmark(campaigns_df, bench_start, as_of_date)

    contexts = {}
    for _, row in pacing_df.iterrows():
        if row["campaign"] == "ACCOUNT TOTAL":
            continue
        month_perf = aggregate(
            campaigns_df[
                (campaigns_df["campaign"] == row["campaign"])
                & (campaigns_df["date"] >= bench_start) & (campaigns_df["date"] <= as_of_date)
            ],
            group_by=None,
        )
        campaign_roas = month_perf.iloc[0]["roas"] if not month_perf.empty else 0.0
        context, commentary = campaign_pacing_context(row["status"], campaign_roas, bench["roas"])
        contexts[row["campaign"]] = {
            "pacing_status": row["status"], "context": context, "commentary": commentary,
            "campaign_roas": campaign_roas, "account_roas": bench["roas"],
        }
    return pacing_df, contexts


# --- Full evidence-based investigation --------------------------------------
def investigate_with_evidence(campaigns_df, changes_df, auction_df, search_terms_df,
                               metric, current_range, previous_range, campaign=None):
    """Everything investigate_range() produces, plus the additional signal
    checks the product spec calls for: search-term quality and budget
    context for the top contributing campaign, an explicit list of
    alternative (non-primary) explanations considered, and a suggested
    next test. Shaped for direct display as an evidence trail."""
    base = investigate_range(campaigns_df, changes_df, auction_df, metric, current_range, previous_range, campaign)

    if not base["verify"]["changed_materially"]:
        base["alternative_explanations"] = []
        base["suggested_next_test"] = None
        return base

    top_campaigns = list(base["hypotheses"].keys())
    bench = account_benchmark(campaigns_df, previous_range[0], current_range[1])

    for camp, hyp in base["hypotheses"].items():
        # Search-term quality: did wasted-spend share rise for this campaign?
        current_waste = waste_share(search_terms_df, camp, *current_range)
        previous_waste = waste_share(search_terms_df, camp, *previous_range)
        hyp["search_term_quality"] = {
            "current_wasted_share": current_waste["wasted_share"],
            "previous_wasted_share": previous_waste["wasted_share"],
            "changed": abs(current_waste["wasted_share"] - previous_waste["wasted_share"]) >= 0.05,
        }

        # Budget context: was this campaign budget-constrained recently?
        pacing_df = compute_pacing(campaigns_df, current_range[1], group_by="campaign")
        camp_pacing = pacing_df[pacing_df["campaign"] == camp]
        hyp["budget_context"] = camp_pacing.iloc[0]["status"] if not camp_pacing.empty else "Unknown"

        hyp["suggested_next_test"] = NEXT_TEST_BY_DRIVER.get(hyp["driver"], NEXT_TEST_BY_DRIVER["unclear"])

    # Alternative explanations: hypothesis drivers that were considered for
    # OTHER contributing campaigns but weren't the account's primary story
    # (base["conclusion"] only narrates the top few) -- surfaced explicitly
    # so the evidence trail doesn't look like it only checked one thing.
    alternatives = []
    for camp, hyp in base["hypotheses"].items():
        if hyp["driver"] not in ("unclear",):
            alternatives.append(f'{camp}: {hyp["text"]} (confidence: {hyp["confidence"]})')
    base["alternative_explanations"] = alternatives
    base["suggested_next_test"] = next(
        (h["suggested_next_test"] for h in base["hypotheses"].values() if h["driver"] != "unclear"),
        NEXT_TEST_BY_DRIVER["unclear"],
    )
    return base
