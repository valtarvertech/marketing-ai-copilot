"""
The Optimization Center's recommendation engine.

Every recommendation is generated from a transparent, named rule applied
to already-calculated facts -- never from an AI model -- and carries the
evidence, expected impact, and confidence behind it so a marketer can
judge whether to act on it. Recommendations never modify a campaign
automatically; they are suggestions for a human to review.

Rules deliberately combine signals from more than one module (pacing +
performance, search-term spend + conversion value, account-level
investigation + contribution) rather than firing off a single threshold
in isolation -- see src/evidence.py for the cross-module composition
this relies on. "Under-pacing" alone never becomes "spend more"; "high
spend" alone never becomes "waste".

This module also carries a small scaffold for tracking whether an
*implemented* recommendation actually worked (recommendation ->
implementation -> observation window -> measured outcome), seeded with
one worked example tied to Scenario E in the synthetic dataset.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from src.metrics import aggregate, favorability
from src.comparisons import week_over_week_range
from src.search_term_intelligence import negative_keyword_candidates, expansion_candidates
from src.keyword_intelligence import classify_keywords, WASTE_CANDIDATE
from src.competitive import auction_trend
from src.executive_brief import generate_brief
from src.evidence import build_pacing_contexts, investigate_with_evidence, NEXT_TEST_BY_DRIVER
from src.evidence import CONTEXT_OPPORTUNITY, CONTEXT_CAUTION, CONTEXT_REVIEW, CONTEXT_AT_RISK, CONTEXT_MONITOR

CATEGORY_HIGH_PRIORITY = "High Priority"
CATEGORY_OPPORTUNITY = "Opportunity"
CATEGORY_INVESTIGATE = "Investigate"
CATEGORY_MONITOR = "Monitor"
CATEGORY_IMPLEMENTED = "Implemented"
CATEGORY_ORDER = [CATEGORY_HIGH_PRIORITY, CATEGORY_OPPORTUNITY, CATEGORY_INVESTIGATE, CATEGORY_MONITOR, CATEGORY_IMPLEMENTED]

STATUS_SUGGESTED = "Suggested"
STATUS_APPROVED = "Approved"
STATUS_IMPLEMENTED = "Implemented"
STATUS_DISMISSED = "Dismissed"


@dataclass
class Recommendation:
    title: str
    entity: str
    category: str
    reason: str
    evidence: str
    expected_impact: str
    confidence: str
    suggested_action: str
    status: str = STATUS_SUGGESTED
    date_implemented: Optional[str] = None
    observation_window_days: Optional[int] = None
    measured_outcome: Optional[str] = None


def _pacing_context_recommendations(campaigns_df, as_of_date):
    """The context-aware pacing logic the product spec calls out
    explicitly: under-pacing only becomes an "Opportunity" when
    efficiency also supports it; otherwise it's flagged for
    investigation, never a blanket "spend more"."""
    _, contexts = build_pacing_contexts(campaigns_df, as_of_date)
    recs = []
    for campaign, ctx in contexts.items():
        context = ctx["context"]
        if context == CONTEXT_AT_RISK:
            recs.append(Recommendation(
                title=f'Review budget efficiency for "{campaign}"', entity=campaign, category=CATEGORY_HIGH_PRIORITY,
                reason="Pacing ahead of budget while returning below-average ROAS.", evidence=ctx["commentary"],
                expected_impact="Avoid overspending on below-average-efficiency traffic; protect blended account ROAS.",
                confidence="High",
                suggested_action="Reduce the daily spend cap or investigate the efficiency drop before month-end.",
            ))
        elif context == CONTEXT_OPPORTUNITY:
            recs.append(Recommendation(
                title=f'Evaluate additional budget for "{campaign}"', entity=campaign, category=CATEGORY_OPPORTUNITY,
                reason="Under-pacing while maintaining ROAS at or above the account average.", evidence=ctx["commentary"],
                expected_impact="Capturing additional eligible traffic could add conversions at a comparable or better efficiency.",
                confidence="Medium",
                suggested_action="Confirm impression-share headroom exists before raising budget or bids -- see Competitive Intelligence.",
            ))
        elif context == CONTEXT_CAUTION:
            recs.append(Recommendation(
                title=f'Investigate "{campaign}" before adjusting budget', entity=campaign, category=CATEGORY_INVESTIGATE,
                reason="Under-pacing, but ROAS is below the account average -- pacing alone doesn't justify more spend.",
                evidence=ctx["commentary"],
                expected_impact="Avoid increasing spend into a below-average-efficiency campaign without understanding why first.",
                confidence="Medium",
                suggested_action="Review recent conversion-rate and CPC trends for this campaign before considering a budget increase.",
            ))
        elif context == CONTEXT_REVIEW:
            recs.append(Recommendation(
                title=f'Review budget headroom for "{campaign}"', entity=campaign, category=CATEGORY_MONITOR,
                reason="Over-pacing but performing at or above the account average.", evidence=ctx["commentary"],
                expected_impact="A budget increase may better match strong demand rather than throttling a working campaign.",
                confidence="Medium",
                suggested_action="Confirm whether additional budget would capture more profitable volume before month-end.",
            ))
        elif context == CONTEXT_MONITOR:
            recs.append(Recommendation(
                title=f'Monitor efficiency for "{campaign}"', entity=campaign, category=CATEGORY_MONITOR,
                reason="Pacing is on track, but ROAS is below the account average.", evidence=ctx["commentary"],
                expected_impact="Early visibility if efficiency continues to slip.", confidence="Low",
                suggested_action="No action needed yet -- revisit next period.",
            ))
    return recs


def _search_term_waste_recommendations(search_terms_df, as_of_date, lookback_days=30, min_spend=25.0):
    window_start = as_of_date - timedelta(days=lookback_days - 1)
    candidates = negative_keyword_candidates(
        search_terms_df, min_spend=min_spend, max_conversions=0, start_date=window_start, end_date=as_of_date,
    )
    recs = []
    for _, row in candidates.iterrows():
        recs.append(Recommendation(
            title=f'Add negative keyword: "{row["search_term"]}"',
            entity=f'{row["campaign"]} / "{row["search_term"]}"', category=CATEGORY_HIGH_PRIORITY,
            reason=f"Spent money with zero conversions over the last {lookback_days} days.",
            evidence=f"Spend ${row['spend']:.2f}, {int(row['clicks'])} clicks, {int(row['conversions'])} conversions.",
            expected_impact="Eliminates confirmed wasted spend; modest CPA improvement for the campaign.",
            confidence="High",
            suggested_action=f'Add "{row["search_term"]}" as a negative keyword on "{row["campaign"]}".',
        ))
    return recs


def _search_term_expansion_recommendations(search_terms_df, as_of_date, lookback_days=30):
    window_start = as_of_date - timedelta(days=lookback_days - 1)
    candidates = expansion_candidates(search_terms_df, start_date=window_start, end_date=as_of_date)
    recs = []
    for _, row in candidates.iterrows():
        recs.append(Recommendation(
            title=f'Consider adding keyword: "{row["search_term"]}"',
            entity=f'{row["campaign"]} / "{row["search_term"]}"', category=CATEGORY_OPPORTUNITY,
            reason="Already converting well without being a dedicated keyword.",
            evidence=f"{int(row['conversions'])} conversions at a {row['conversion_rate']:.1%} conversion rate, "
                     f"ROAS {row['roas']:.2f}x over the last {lookback_days} days.",
            expected_impact="Dedicated keyword-level control (bid, match type) over already-proven demand.",
            confidence="Medium",
            suggested_action=f'Add "{row["search_term"]}" as a keyword on "{row["campaign"]}" and monitor bid/match type.',
        ))
    return recs


def _keyword_waste_recommendations(keywords_df, as_of_date, lookback_days=30):
    window_start = as_of_date - timedelta(days=lookback_days - 1)
    classified = classify_keywords(keywords_df, start_date=window_start, end_date=as_of_date)
    if classified.empty:
        return []
    waste = classified[classified["status"] == WASTE_CANDIDATE]
    recs = []
    for _, row in waste.iterrows():
        recs.append(Recommendation(
            title=f'Review keyword: "{row["keyword"]}"', entity=f'{row["campaign"]} / "{row["keyword"]}"',
            category=CATEGORY_INVESTIGATE,
            reason="High spend relative to other keywords in the account, with ROAS below 1.0x.",
            evidence=f"Spend ${row['spend']:.2f}, ROAS {row['roas']:.2f}x, {int(row['conversions'])} conversions.",
            expected_impact="A bid or match-type adjustment could reduce spend without losing profitable volume.",
            confidence="Medium",
            suggested_action="Review bid strategy and match type; consider a bid reduction if the pattern persists.",
        ))
    return recs


def _competitive_pressure_recommendations(campaigns_df, auction_df, threshold=0.05):
    cur_start, cur_end, prev_start, prev_end = week_over_week_range(campaigns_df)
    recs = []
    for campaign in sorted(campaigns_df["campaign"].unique()):
        trend = auction_trend(auction_df, campaign, (cur_start, cur_end), (prev_start, prev_end))
        rank = trend["lost_is_rank"]
        if rank["current"] is None or rank["previous"] is None:
            continue
        if (rank["current"] - rank["previous"]) >= threshold:
            recs.append(Recommendation(
                title=f'Rising rank pressure on "{campaign}"', entity=campaign, category=CATEGORY_INVESTIGATE,
                reason="Lost impression share due to rank rose week over week, consistent with a competitor "
                       "outranking this campaign more often.",
                evidence=f"Lost IS (Rank): {rank['previous']:.1%} -> {rank['current']:.1%}. "
                         f"Most recently observed top competitor: {trend['top_competitor']}.",
                expected_impact="Understanding whether this is a bid, ad rank, or quality issue before reacting on cost alone.",
                confidence="Medium",
                suggested_action="Review Competitive Intelligence for this campaign; consider bid strategy or ad rank levers.",
            ))
    return recs


def _investigation_recommendation(campaigns_df, changes_df, auction_df, search_terms_df):
    """One recommendation tied to the single most material account-level
    issue this week (reusing executive_brief's own worst-metric logic so
    Optimization Center never disagrees with the Executive Overview brief),
    with the full evidence trail and suggested next test attached."""
    brief = generate_brief(campaigns_df)
    if brief["worst_metric"] is None:
        return []

    metric = brief["worst_metric"]
    current_range = week_over_week_range(campaigns_df)[0:2]
    previous_range = week_over_week_range(campaigns_df)[2:4]
    report = investigate_with_evidence(
        campaigns_df, changes_df, auction_df, search_terms_df, metric, current_range, previous_range
    )
    if not report["hypotheses"]:
        return []

    top_campaign = next(iter(report["hypotheses"]))
    top_hyp = report["hypotheses"][top_campaign]
    return [Recommendation(
        title=f"Investigate {metric.replace('_', ' ')} change",
        entity=top_campaign, category=CATEGORY_INVESTIGATE,
        reason=report["conclusion"],
        evidence="Full evidence trail available in Campaign Intelligence's investigation tool "
                 f"({top_campaign}, {metric.replace('_', ' ')}, week over week).",
        expected_impact="A targeted fix based on the actual driver, rather than a broad, unproven action.",
        confidence=top_hyp.get("confidence", "Low"),
        suggested_action=report.get("suggested_next_test") or NEXT_TEST_BY_DRIVER["unclear"],
    )]


def generate_recommendations(campaigns_df, keywords_df, search_terms_df, changes_df, auction_df, as_of_date):
    """Run every recommendation rule and return a combined list, ordered
    by category severity (High Priority first)."""
    recs = []
    recs.extend(_pacing_context_recommendations(campaigns_df, as_of_date))
    recs.extend(_search_term_waste_recommendations(search_terms_df, as_of_date))
    recs.extend(_search_term_expansion_recommendations(search_terms_df, as_of_date))
    recs.extend(_keyword_waste_recommendations(keywords_df, as_of_date))
    recs.extend(_competitive_pressure_recommendations(campaigns_df, auction_df))
    recs.extend(_investigation_recommendation(campaigns_df, changes_df, auction_df, search_terms_df))

    order = {cat: i for i, cat in enumerate(CATEGORY_ORDER)}
    return sorted(recs, key=lambda r: order.get(r.category, len(order)))


def seed_tracked_recommendation_example(campaigns_df, changes_df):
    """Build one fully worked "recommendation -> implementation ->
    observation window -> measured outcome" example from the Scenario E
    data (negative keywords added to Remarketing), to demonstrate the
    impact-tracking framework end to end with a real, computed result
    rather than a placeholder."""
    change_row = changes_df[
        (changes_df["campaign"] == "Remarketing") & (changes_df["change_type"] == "negative_keyword_added")
    ]
    if change_row.empty:
        return None
    implemented_date = change_row.iloc[0]["date"]
    observation_window_days = 10

    before_start = implemented_date - timedelta(days=observation_window_days)
    before_end = implemented_date - timedelta(days=1)
    after_start = implemented_date + timedelta(days=1)
    after_end = implemented_date + timedelta(days=observation_window_days)

    remarketing = campaigns_df[campaigns_df["campaign"] == "Remarketing"]
    before = aggregate(remarketing[(remarketing["date"] >= before_start) & (remarketing["date"] <= before_end)])
    after = aggregate(remarketing[(remarketing["date"] >= after_start) & (remarketing["date"] <= after_end)])

    before_cpa = before["cpa"].iloc[0]
    after_cpa = after["cpa"].iloc[0]
    pct_change = (after_cpa - before_cpa) / before_cpa if before_cpa else None

    outcome = (
        f"CPA moved from ${before_cpa:.2f} to ${after_cpa:.2f} ({pct_change:+.1%}) over the "
        f"{observation_window_days} days after implementation."
        if pct_change is not None else "Not enough data to measure outcome."
    )

    return Recommendation(
        title="Add negative keywords to cut irrelevant remarketing triggers",
        entity="Remarketing", category=CATEGORY_IMPLEMENTED,
        reason="Irrelevant search terms were consuming clicks without converting.",
        evidence="See changes.csv (negative_keyword_added, Remarketing) and search_terms.csv.",
        expected_impact="Lower CPA from reduced wasted spend.", confidence="Medium",
        suggested_action="Monitor for another observation window to confirm the improvement holds.",
        status=STATUS_IMPLEMENTED, date_implemented=str(implemented_date),
        observation_window_days=observation_window_days, measured_outcome=outcome,
    )
