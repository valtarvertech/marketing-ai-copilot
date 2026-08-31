"""
Synthetic data generator for Marketing AI Copilot.

Generates ~90 days of realistic (but entirely fictional) daily advertising
performance data for a fictional telecom company, "ConnectWave
Communications", plus supporting datasets for keywords, search terms,
account changes, and auction/competitive insights.

This is NOT real advertiser data. All numbers are synthetically generated
with a fixed random seed so the dataset is reproducible. On top of random
day-to-day noise, we deliberately inject a handful of "scenarios" -- known,
documented performance stories (e.g. rising CPC due to competitive
pressure, a conversion-rate drop caused by a landing page change) so the
investigation engine can later be tested against a known ground truth
(see scenario_ground_truth.csv).

Run with:  python3 scripts/generate_synthetic_data.py
"""

import csv
import random
from datetime import date, timedelta

random.seed(42)

OUTPUT_DIR = "data"
TOTAL_DAYS = 90
END_DATE = date(2026, 8, 29)  # most recent day in the dataset
START_DATE = END_DATE - timedelta(days=TOTAL_DAYS - 1)

ALL_DATES = [START_DATE + timedelta(days=i) for i in range(TOTAL_DAYS)]


def day_index(d):
    """Return 0-based index of a date within the dataset (0 = START_DATE)."""
    return (d - START_DATE).days


# ---------------------------------------------------------------------------
# Campaign baseline configuration
# ---------------------------------------------------------------------------
# These baselines are loosely anchored to the Sprint 1 single-day mock
# numbers so the new dataset feels like a natural extension of the old one.
CAMPAIGNS = {
    "Brand Search": dict(
        channel="Paid Search", campaign_type="Brand",
        impressions=18500, ctr=0.080, cpc=2.20, cvr=0.1297, aov=200.0,
        monthly_budget=112000,
    ),
    "Business Fiber": dict(
        channel="Paid Search", campaign_type="Non-Brand",
        impressions=42500, ctr=0.050, cpc=3.80, cvr=0.0649, aov=300.0,
        monthly_budget=279000,
    ),
    "SD-WAN": dict(
        channel="Paid Search", campaign_type="Non-Brand",
        impressions=28750, ctr=0.040, cpc=5.50, cvr=0.0643, aov=450.0,
        monthly_budget=218000,
    ),
    "UCaaS": dict(
        channel="Paid Search", campaign_type="Non-Brand",
        impressions=31800, ctr=0.040, cpc=4.50, cvr=0.0700, aov=400.0,
        monthly_budget=197000,
    ),
    "Managed Security": dict(
        channel="Paid Search", campaign_type="Non-Brand",
        impressions=24300, ctr=0.035, cpc=6.00, cvr=0.0599, aov=550.0,
        monthly_budget=176000,
    ),
    "Enterprise Voice": dict(
        channel="Paid Search", campaign_type="Non-Brand",
        impressions=19600, ctr=0.040, cpc=5.50, cvr=0.0587, aov=500.0,
        monthly_budget=149000,
    ),
    "Remarketing": dict(
        channel="Display", campaign_type="Remarketing",
        impressions=67200, ctr=0.014, cpc=3.00, cvr=0.0670, aov=300.0,
        monthly_budget=97000,
    ),
}

PLATFORM = "Google Ads"

# Day-of-week multiplier: B2B telecom traffic dips on weekends.
DOW_MULTIPLIER = {
    0: 1.05,  # Monday
    1: 1.08,  # Tuesday
    2: 1.05,  # Wednesday
    3: 1.02,  # Thursday
    4: 0.95,  # Friday
    5: 0.55,  # Saturday
    6: 0.55,  # Sunday
}


def noise(spread=0.08):
    """Small random multiplicative noise, e.g. 0.08 = +/-8%."""
    return 1.0 + random.uniform(-spread, spread)


# ---------------------------------------------------------------------------
# Scenario windows (documented in scenario_ground_truth.csv)
# ---------------------------------------------------------------------------
SCENARIO_A_CPC_PRESSURE = (day_index(END_DATE) - 34, day_index(END_DATE) - 15)     # Enterprise Voice
SCENARIO_B_CVR_DECLINE = (day_index(END_DATE) - 49, day_index(END_DATE) - 35)      # Business Fiber
SCENARIO_C_BUDGET_CONSTRAINT = (day_index(END_DATE) - 29, day_index(END_DATE))     # SD-WAN (runs through end)
SCENARIO_D_SEARCH_TERM_WASTE = (day_index(END_DATE) - 24, day_index(END_DATE))     # Managed Security (runs through end)
SCENARIO_E_POSITIVE_OPT_CHANGE_DAY = day_index(END_DATE) - 14                       # Remarketing
SCENARIO_E_WINDOW = (SCENARIO_E_POSITIVE_OPT_CHANGE_DAY + 1, SCENARIO_E_POSITIVE_OPT_CHANGE_DAY + 10)

SD_WAN_BUDGET_CUT_DAY = SCENARIO_C_BUDGET_CONSTRAINT[0] - 2
SD_WAN_BUDGET_AFTER_CUT = 155000

# Scenario F: spend rises (CPC creep, e.g. broader manual bid increases)
# while clicks/conversions stay flat, so CPA rises mechanically -- UCaaS,
# last 30 days. This also makes UCaaS the "under-pacing but weak recent
# efficiency, don't just scale it" story for Budget Pacing, distinct from
# Brand Search's "under-pacing with strong efficiency, real opportunity"
# story (Brand Search needs no overlay -- it's already the account's
# strongest, untouched performer).
SCENARIO_F_SPEND_UP_FLAT_CONVERSIONS = (day_index(END_DATE) - 29, day_index(END_DATE))  # UCaaS

# Scenario I: the account's most recent 7-day window shows a material
# (>5%) conversion decline, so "Why did conversions decrease?" in Ask My
# Account has something real to investigate. Two campaigns contribute,
# with different evidence profiles on purpose:
#   - SD-WAN: Scenario C's existing budget constraint compounds further
#     in the final stretch (demand keeps outpacing the capped budget) --
#     same underlying cause as before, same budget_decreased change
#     event, just a steeper effect. High-confidence, well-corroborated.
#   - Business Fiber: a second, smaller conversion-rate softening with
#     NO corroborating change-log entry this time (unlike Scenario B's
#     landing-page regression) -- deliberately, so the engine's
#     "alternative explanation" for the account-level decline is a real
#     material signal with lower confidence, not a fabricated one.
SCENARIO_I_RECENT_DECLINE_WINDOW = (day_index(END_DATE) - 9, day_index(END_DATE))


def in_window(idx, window):
    return window[0] <= idx <= window[1]


def generate_campaign_row(campaign_name, d):
    idx = day_index(d)
    cfg = CAMPAIGNS[campaign_name]

    impressions = cfg["impressions"]
    ctr = cfg["ctr"]
    cpc = cfg["cpc"]
    cvr = cfg["cvr"]
    aov = cfg["aov"]
    monthly_budget = cfg["monthly_budget"]

    dow_mult = DOW_MULTIPLIER[d.weekday()]

    # --- scenario overlays -------------------------------------------------
    if campaign_name == "Enterprise Voice" and in_window(idx, SCENARIO_A_CPC_PRESSURE):
        # Competitive pressure: CPC ramps up while traffic stays roughly flat.
        progress = (idx - SCENARIO_A_CPC_PRESSURE[0]) / max(1, SCENARIO_A_CPC_PRESSURE[1] - SCENARIO_A_CPC_PRESSURE[0])
        cpc *= 1.0 + 0.45 * min(1.0, progress + 0.15)

    if campaign_name == "Business Fiber" and in_window(idx, SCENARIO_B_CVR_DECLINE):
        # Landing page regression: conversion rate drops, traffic unaffected.
        cvr *= 0.65

    if campaign_name == "Business Fiber" and in_window(idx, SCENARIO_I_RECENT_DECLINE_WINDOW):
        # A second, smaller, unexplained conversion-rate softening --
        # deliberately no associated change-log entry (see Scenario I note above).
        cvr *= 0.72

    if campaign_name == "Remarketing" and in_window(idx, SCENARIO_E_WINDOW):
        # Positive optimization: negative keywords cut irrelevant traffic,
        # conversion rate improves, traffic otherwise unaffected.
        cvr *= 1.18

    if campaign_name == "UCaaS" and in_window(idx, SCENARIO_F_SPEND_UP_FLAT_CONVERSIONS):
        # CPC creeps up (e.g. broader manual bidding) while clicks/CVR stay
        # put -- conversions stay flat, spend and CPA rise mechanically.
        progress = (idx - SCENARIO_F_SPEND_UP_FLAT_CONVERSIONS[0]) / max(
            1, SCENARIO_F_SPEND_UP_FLAT_CONVERSIONS[1] - SCENARIO_F_SPEND_UP_FLAT_CONVERSIONS[0]
        )
        cpc *= 1.0 + 0.30 * min(1.0, progress + 0.15)

    if campaign_name == "SD-WAN":
        if idx >= SD_WAN_BUDGET_CUT_DAY:
            monthly_budget = SD_WAN_BUDGET_AFTER_CUT
        if in_window(idx, SCENARIO_C_BUDGET_CONSTRAINT):
            # Budget-limited: demand exists but spend (and therefore
            # impressions/clicks) is capped below natural levels.
            impressions *= 0.72
            # CTR/CPC stay ~stable -- this is a volume story, not an
            # efficiency story.
        if in_window(idx, SCENARIO_I_RECENT_DECLINE_WINDOW):
            # The constraint compounds further in the final stretch --
            # same capped budget, but demand has kept growing against it.
            impressions *= 0.72

    if campaign_name == "Managed Security" and in_window(idx, SCENARIO_D_SEARCH_TERM_WASTE):
        # A batch of irrelevant search terms starts consuming spend with
        # ~no conversions. Modeled here as extra "wasted" clicks/spend on
        # top of the normal campaign, dragging blended CVR/CPA down.
        waste_share = 0.15
        extra_clicks = impressions * ctr * waste_share
        extra_spend = extra_clicks * cpc
        wasted_impressions = extra_clicks / ctr
        base_impressions = impressions * dow_mult * noise()
        base_clicks = base_impressions * ctr
        base_spend = base_clicks * cpc
        base_conversions = base_clicks * cvr

        impressions_total = base_impressions + wasted_impressions * dow_mult * noise()
        clicks_total = base_clicks + extra_clicks * dow_mult * noise()
        spend_total = base_spend + extra_spend * dow_mult * noise()
        conversions_total = base_conversions  # wasted clicks convert at ~0%
        conversion_value_total = conversions_total * aov

        return _round_row(
            d, campaign_name, cfg, impressions_total, clicks_total,
            spend_total, conversions_total, conversion_value_total,
            monthly_budget,
        )

    # --- standard (non-overlay) row calculation -----------------------------
    day_impressions = impressions * dow_mult * noise()
    day_clicks = day_impressions * ctr * noise(0.05)
    day_spend = day_clicks * cpc * noise(0.05)
    day_conversions = day_clicks * cvr * noise(0.10)
    day_conversion_value = day_conversions * aov * noise(0.05)

    return _round_row(
        d, campaign_name, cfg, day_impressions, day_clicks, day_spend,
        day_conversions, day_conversion_value, monthly_budget,
    )


def _round_row(d, campaign_name, cfg, impressions, clicks, spend,
                conversions, conversion_value, monthly_budget):
    clicks = min(clicks, impressions)
    conversions = min(conversions, clicks)
    return {
        "date": d.isoformat(),
        "platform": PLATFORM,
        "channel": cfg["channel"],
        "campaign": campaign_name,
        "campaign_type": cfg["campaign_type"],
        "impressions": int(round(impressions)),
        "clicks": int(round(clicks)),
        "spend": round(spend, 2),
        "conversions": int(round(conversions)),
        "conversion_value": round(conversion_value, 2),
        "monthly_budget": round(monthly_budget, 2),
    }


def generate_campaigns():
    rows = []
    for d in ALL_DATES:
        for campaign_name in CAMPAIGNS:
            rows.append(generate_campaign_row(campaign_name, d))
    return rows


# ---------------------------------------------------------------------------
# Keywords (last 30 days, paid search campaigns only)
# ---------------------------------------------------------------------------
KEYWORD_MAP = {
    "Brand Search": [
        ("connectwave", "Exact", 0.50),
        ("connectwave communications", "Phrase", 0.30),
        ("connectwave login", "Exact", 0.20),
    ],
    "Business Fiber": [
        ("business fiber internet", "Phrase", 0.45),
        ("fiber internet for business", "Phrase", 0.30),
        ("dedicated fiber connection", "Broad", 0.25),
    ],
    "SD-WAN": [
        ("sd-wan provider", "Phrase", 0.45),
        ("sd-wan solutions", "Phrase", 0.30),
        ("managed sd-wan", "Broad", 0.25),
    ],
    "UCaaS": [
        ("ucaas provider", "Phrase", 0.40),
        ("cloud phone system", "Phrase", 0.35),
        ("business voip solutions", "Broad", 0.25),
    ],
    "Managed Security": [
        ("managed security services", "Phrase", 0.40),
        ("network security provider", "Phrase", 0.30),
        ("endpoint security business", "Broad", 0.30),
    ],
    "Enterprise Voice": [
        ("enterprise voice solutions", "Phrase", 0.40),
        ("sip trunking provider", "Phrase", 0.35),
        ("business phone systems", "Broad", 0.25),
    ],
}

KEYWORD_HISTORY_DAYS = 30


def generate_keywords(campaign_rows):
    """Split each paid-search campaign's daily totals across a small set of
    representative keywords, using fixed weights plus light noise."""
    by_date_campaign = {(r["date"], r["campaign"]): r for r in campaign_rows}
    rows = []
    recent_dates = ALL_DATES[-KEYWORD_HISTORY_DAYS:]
    for d in recent_dates:
        for campaign_name, keywords in KEYWORD_MAP.items():
            campaign_row = by_date_campaign[(d.isoformat(), campaign_name)]
            for keyword, match_type, weight in keywords:
                w = weight * noise(0.06)
                rows.append({
                    "date": d.isoformat(),
                    "platform": PLATFORM,
                    "campaign": campaign_name,
                    "keyword": keyword,
                    "match_type": match_type,
                    "impressions": int(round(campaign_row["impressions"] * w)),
                    "clicks": int(round(campaign_row["clicks"] * w)),
                    "spend": round(campaign_row["spend"] * w, 2),
                    "conversions": int(round(campaign_row["conversions"] * w)),
                    "conversion_value": round(campaign_row["conversion_value"] * w, 2),
                })
    return rows


# ---------------------------------------------------------------------------
# Search terms (last 30 days). Managed Security gets an injected batch of
# high-spend, zero-conversion "waste" terms starting at the Scenario D
# window to power search-term-waste detection.
# ---------------------------------------------------------------------------
NORMAL_SEARCH_TERMS = {
    "Brand Search": [("connectwave", "connectwave")],
    "Business Fiber": [("best business fiber plans", "business fiber internet")],
    "SD-WAN": [("top sd-wan vendors", "sd-wan provider")],
    "UCaaS": [("ucaas pricing comparison", "ucaas provider")],
    "Managed Security": [("managed security services cost", "managed security services")],
    "Enterprise Voice": [("enterprise voice pricing", "enterprise voice solutions")],
}

WASTE_SEARCH_TERMS = [
    "free network security tips",
    "network security jobs near me",
    "what is network security",
]


def generate_search_terms():
    rows = []
    recent_dates = ALL_DATES[-KEYWORD_HISTORY_DAYS:]
    for d in recent_dates:
        idx = day_index(d)
        for campaign_name, terms in NORMAL_SEARCH_TERMS.items():
            for term, matched_keyword in terms:
                clicks = max(1, int(round(20 * noise(0.2))))
                impressions = int(round(clicks / 0.06))
                spend = round(clicks * CAMPAIGNS[campaign_name]["cpc"] * noise(0.1), 2)
                conversions = int(round(clicks * CAMPAIGNS[campaign_name]["cvr"] * noise(0.3)))
                conversion_value = round(conversions * CAMPAIGNS[campaign_name]["aov"], 2)
                rows.append({
                    "date": d.isoformat(), "platform": PLATFORM, "campaign": campaign_name,
                    "search_term": term, "matched_keyword": matched_keyword,
                    "impressions": impressions, "clicks": clicks, "spend": spend,
                    "conversions": conversions, "conversion_value": conversion_value,
                })

        if in_window(idx, SCENARIO_D_SEARCH_TERM_WASTE):
            for term in WASTE_SEARCH_TERMS:
                clicks = max(1, int(round(14 * noise(0.25))))
                impressions = int(round(clicks / 0.04))
                spend = round(clicks * CAMPAIGNS["Managed Security"]["cpc"] * noise(0.1), 2)
                rows.append({
                    "date": d.isoformat(), "platform": PLATFORM, "campaign": "Managed Security",
                    "search_term": term, "matched_keyword": "managed security services",
                    "impressions": impressions, "clicks": clicks, "spend": spend,
                    "conversions": 0, "conversion_value": 0.0,
                })
    return rows


# ---------------------------------------------------------------------------
# Account change history
# ---------------------------------------------------------------------------
def generate_changes():
    d = lambda offset: (END_DATE - timedelta(days=day_index(END_DATE) - offset)).isoformat()
    return [
        {
            "date": d(10), "platform": PLATFORM, "campaign": "Brand Search",
            "entity": "Ad Creative", "change_type": "creative_updated",
            "old_value": "Headline v1", "new_value": "Headline v2",
            "changed_by": "Marketing Team", "notes": "Refreshed ad copy, no measurable performance shift.",
        },
        {
            "date": d(20), "platform": PLATFORM, "campaign": "UCaaS",
            "entity": "Targeting", "change_type": "targeting_changed",
            "old_value": "National", "new_value": "National + top 20 metros priority",
            "changed_by": "PPC Team", "notes": "Added geo bid adjustments, minimal observed impact.",
        },
        {
            "date": d(SCENARIO_B_CVR_DECLINE[0] - 1), "platform": PLATFORM, "campaign": "Business Fiber",
            "entity": "Landing Page", "change_type": "landing_page_changed",
            "old_value": "v3-template", "new_value": "v4-template",
            "changed_by": "Marketing Team", "notes": "Redesigned lead form on the Business Fiber landing page.",
        },
        {
            "date": d(SCENARIO_A_CPC_PRESSURE[0] - 1), "platform": PLATFORM, "campaign": "Enterprise Voice",
            "entity": "Bid Strategy", "change_type": "bid_strategy_changed",
            "old_value": "Manual CPC", "new_value": "Target CPA",
            "changed_by": "PPC Team", "notes": "Switched to automated bidding around the same time CPC began rising.",
        },
        {
            "date": d(SD_WAN_BUDGET_CUT_DAY), "platform": PLATFORM, "campaign": "SD-WAN",
            "entity": "Budget", "change_type": "budget_decreased",
            "old_value": "$218,000/mo", "new_value": "$155,000/mo",
            "changed_by": "Finance", "notes": "Budget reduced as part of Q3 reallocation.",
        },
        {
            "date": d(SCENARIO_E_POSITIVE_OPT_CHANGE_DAY), "platform": PLATFORM, "campaign": "Remarketing",
            "entity": "Search Terms", "change_type": "negative_keyword_added",
            "old_value": "", "new_value": "-jobs, -free, -tutorial",
            "changed_by": "PPC Team", "notes": "Added negative keywords to cut irrelevant remarketing triggers.",
        },
    ]


# ---------------------------------------------------------------------------
# Auction / competitive insights (weekly grain per campaign)
# ---------------------------------------------------------------------------
COMPETITORS = ["Verizon", "AT&T", "Comcast Business", "Lumen", "Spectrum Business"]
CAMPAIGN_COMPETITORS = {
    "Brand Search": "AT&T",
    "Business Fiber": "Comcast Business",
    "SD-WAN": "Lumen",
    "UCaaS": "Verizon",
    "Managed Security": "Lumen",
    "Enterprise Voice": "AT&T",
    "Remarketing": "Spectrum Business",
}


def generate_auction_insights():
    rows = []
    week_starts = ALL_DATES[0::7]
    for week_start in week_starts:
        idx = day_index(week_start)
        for campaign_name in CAMPAIGNS:
            impression_share = 0.55 * noise(0.08)
            outranking_share = 0.50 * noise(0.08)
            lost_is_rank = 0.20 * noise(0.15)
            lost_is_budget = 0.10 * noise(0.15)

            if campaign_name == "Enterprise Voice" and in_window(idx, SCENARIO_A_CPC_PRESSURE):
                outranking_share *= 0.7
                lost_is_rank *= 1.8
                impression_share *= 0.85

            if campaign_name == "SD-WAN" and in_window(idx, SCENARIO_C_BUDGET_CONSTRAINT):
                lost_is_budget *= 2.6
                impression_share *= 0.75

            lost_is_rank = min(lost_is_rank, 0.9)
            lost_is_budget = min(lost_is_budget, 0.9)
            impression_share = max(0.05, min(impression_share, 0.95))

            rows.append({
                "week_start_date": week_start.isoformat(),
                "platform": PLATFORM,
                "campaign": campaign_name,
                "impression_share": round(impression_share, 3),
                "overlap_rate": round(0.35 * noise(0.1), 3),
                "position_above_rate": round(0.45 * noise(0.1), 3),
                "top_of_page_rate": round(0.60 * noise(0.08), 3),
                "absolute_top_rate": round(0.25 * noise(0.1), 3),
                "outranking_share": round(outranking_share, 3),
                "lost_is_rank": round(lost_is_rank, 3),
                "lost_is_budget": round(lost_is_budget, 3),
                "top_competitor": CAMPAIGN_COMPETITORS[campaign_name],
            })
    return rows


# ---------------------------------------------------------------------------
# Ground truth (for automated testing of the investigation engine)
# ---------------------------------------------------------------------------
def generate_scenario_ground_truth():
    d_start = lambda idx: (START_DATE + timedelta(days=idx)).isoformat()
    d_end = lambda idx: (START_DATE + timedelta(days=idx)).isoformat()
    return [
        {
            "scenario_id": "A", "campaign": "Enterprise Voice",
            "start_date": d_start(SCENARIO_A_CPC_PRESSURE[0]), "end_date": d_end(SCENARIO_A_CPC_PRESSURE[1]),
            "expected_primary_driver": "cpc_increase_competitive_pressure",
            "description": "CPC rises ~45% due to competitive pressure (rising competitor outranking share); "
                            "clicks/impressions stay roughly flat. A bid-strategy change happened the day before "
                            "this window started -- the investigation engine should treat it as a correlated, "
                            "not necessarily causal, event and weigh the auction-insights evidence more heavily.",
            "related_change_event": "bid_strategy_changed (Enterprise Voice)",
            "related_auction_signal": "rising lost_is_rank / falling outranking_share for Enterprise Voice",
        },
        {
            "scenario_id": "B", "campaign": "Business Fiber",
            "start_date": d_start(SCENARIO_B_CVR_DECLINE[0]), "end_date": d_end(SCENARIO_B_CVR_DECLINE[1]),
            "expected_primary_driver": "conversion_rate_decline",
            "description": "Conversion rate drops ~35% relative while clicks/impressions stay normal, "
                            "one day after a landing page template change.",
            "related_change_event": "landing_page_changed (Business Fiber)",
            "related_auction_signal": "none expected",
        },
        {
            "scenario_id": "C", "campaign": "SD-WAN",
            "start_date": d_start(SCENARIO_C_BUDGET_CONSTRAINT[0]), "end_date": d_end(SCENARIO_C_BUDGET_CONSTRAINT[1]),
            "expected_primary_driver": "volume_decline_budget_constrained",
            "description": "Impressions/clicks/conversions fall ~28% while CTR/CPC stay stable, after a monthly "
                            "budget cut. Auction insights show rising lost impression share due to budget "
                            "(not rank), distinguishing this from a competitive/CPC story.",
            "related_change_event": "budget_decreased (SD-WAN)",
            "related_auction_signal": "rising lost_is_budget for SD-WAN",
        },
        {
            "scenario_id": "D", "campaign": "Managed Security",
            "start_date": d_start(SCENARIO_D_SEARCH_TERM_WASTE[0]), "end_date": d_end(SCENARIO_D_SEARCH_TERM_WASTE[1]),
            "expected_primary_driver": "search_term_waste",
            "description": "A batch of irrelevant, high-spend, zero-conversion search terms begins consuming "
                            "~15% of campaign clicks/spend, dragging down blended conversion rate and CPA "
                            "even though core keywords are unaffected.",
            "related_change_event": "none",
            "related_auction_signal": "none expected",
        },
        {
            "scenario_id": "E", "campaign": "Remarketing",
            "start_date": d_start(SCENARIO_E_WINDOW[0]), "end_date": d_end(SCENARIO_E_WINDOW[1]),
            "expected_primary_driver": "positive_optimization",
            "description": "Conversion rate improves ~18% in the 10 days following a negative-keyword addition, "
                            "demonstrating a recommendation whose implementation can be tied to a measured "
                            "positive outcome.",
            "related_change_event": "negative_keyword_added (Remarketing)",
            "related_auction_signal": "none expected",
        },
        {
            "scenario_id": "F", "campaign": "UCaaS",
            "start_date": d_start(SCENARIO_F_SPEND_UP_FLAT_CONVERSIONS[0]),
            "end_date": d_end(SCENARIO_F_SPEND_UP_FLAT_CONVERSIONS[1]),
            "expected_primary_driver": "spend_up_conversions_flat",
            "description": "CPC rises ~30% over the last 30 days while clicks and conversion rate stay flat, so "
                            "conversions stay roughly flat while spend and CPA both rise. This also makes UCaaS "
                            "an 'under-pacing but recently weaker efficiency' case for Budget Pacing -- scaling "
                            "spend further is not obviously appropriate here, unlike Brand Search (see G).",
            "related_change_event": "none",
            "related_auction_signal": "none expected",
        },
        {
            "scenario_id": "G", "campaign": "Brand Search",
            "start_date": ALL_DATES[0].isoformat(), "end_date": ALL_DATES[-1].isoformat(),
            "expected_primary_driver": "stable_high_performer",
            "description": "No scenario overlay is applied to Brand Search -- it is the account's stable, "
                            "highest-ROAS, highest-conversion-rate campaign throughout the dataset. Combined with "
                            "its baseline 15% budget headroom, it is naturally under-pacing while performing "
                            "strongly, illustrating a genuine 'opportunity to scale' pacing story (contrast "
                            "with UCaaS's scenario F, an under-pacing campaign that should NOT simply be scaled).",
            "related_change_event": "none",
            "related_auction_signal": "none expected",
        },
        {
            "scenario_id": "H", "campaign": "Managed Security / Business Fiber / SD-WAN / Enterprise Voice",
            "start_date": ALL_DATES[-KEYWORD_HISTORY_DAYS].isoformat(), "end_date": ALL_DATES[-1].isoformat(),
            "expected_primary_driver": "keyword_expansion_candidates",
            "description": "Several non-brand search terms (e.g. 'ucaas pricing comparison', 'best business "
                            "fiber plans') already convert well enough over the last 30 days to qualify as "
                            "keyword-expansion candidates under search_term_intelligence.expansion_candidates() "
                            "-- an emergent property of the baseline data, not an injected anomaly. Ambiguity is "
                            "intentional: not every qualifying term is equally strong, mirroring real accounts.",
            "related_change_event": "none",
            "related_auction_signal": "none expected",
        },
        {
            "scenario_id": "I", "campaign": "SD-WAN / Business Fiber",
            "start_date": (START_DATE + timedelta(days=SCENARIO_I_RECENT_DECLINE_WINDOW[0])).isoformat(),
            "end_date": ALL_DATES[-1].isoformat(),
            "expected_primary_driver": "account_level_conversion_decline",
            "description": "The account's most recent 7-day window shows a material (>5%) conversion decline, "
                            "driven by two distinct campaign stories: SD-WAN's existing budget constraint "
                            "(Scenario C) compounds further in the final 10 days (same cause, same "
                            "budget_decreased change event, steeper effect -- high confidence), and Business "
                            "Fiber develops a second, smaller conversion-rate softening with NO corroborating "
                            "change-log entry this time, unlike Scenario B's landing-page regression (lower "
                            "confidence, a genuine 'alternative explanation'). Exists to give Ask My Account's "
                            "'Why did conversions decrease?' a real, calculated investigation to demonstrate, "
                            "not a hard-coded one.",
            "related_change_event": "budget_decreased (SD-WAN)",
            "related_auction_signal": "rising lost_is_budget for SD-WAN",
        },
    ]


# ---------------------------------------------------------------------------
# Write CSVs
# ---------------------------------------------------------------------------
def write_csv(filename, rows, fieldnames):
    path = f"{OUTPUT_DIR}/{filename}"
    with open(path, mode="w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {path}")


def main():
    campaign_rows = generate_campaigns()
    write_csv("campaigns.csv", campaign_rows, [
        "date", "platform", "channel", "campaign", "campaign_type",
        "impressions", "clicks", "spend", "conversions", "conversion_value",
        "monthly_budget",
    ])

    keyword_rows = generate_keywords(campaign_rows)
    write_csv("keywords.csv", keyword_rows, [
        "date", "platform", "campaign", "keyword", "match_type",
        "impressions", "clicks", "spend", "conversions", "conversion_value",
    ])

    search_term_rows = generate_search_terms()
    write_csv("search_terms.csv", search_term_rows, [
        "date", "platform", "campaign", "search_term", "matched_keyword",
        "impressions", "clicks", "spend", "conversions", "conversion_value",
    ])

    change_rows = generate_changes()
    write_csv("changes.csv", change_rows, [
        "date", "platform", "campaign", "entity", "change_type",
        "old_value", "new_value", "changed_by", "notes",
    ])

    auction_rows = generate_auction_insights()
    write_csv("auction_insights.csv", auction_rows, [
        "week_start_date", "platform", "campaign", "impression_share",
        "overlap_rate", "position_above_rate", "top_of_page_rate",
        "absolute_top_rate", "outranking_share", "lost_is_rank",
        "lost_is_budget", "top_competitor",
    ])

    ground_truth_rows = generate_scenario_ground_truth()
    write_csv("scenario_ground_truth.csv", ground_truth_rows, [
        "scenario_id", "campaign", "start_date", "end_date",
        "expected_primary_driver", "description", "related_change_event",
        "related_auction_signal",
    ])


if __name__ == "__main__":
    main()
