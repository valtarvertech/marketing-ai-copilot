"""
"Ask My Account" -- a deterministic question router.

This is intentionally NOT a natural-language AI interface. It matches a
fixed set of question patterns (keyword/regex based) to the relevant
analysis function(s) and formats a plain-English answer from real,
calculated numbers. No external LLM is required for this to work.

Where a question implies a causal investigation ("why did X change?"),
the router walks the same multi-step chain a human analyst would --
verify, quantify, localize, check traffic, check conversion rate, check
search-term quality, check budget, check competitive pressure, check
recent changes -- via src/evidence.py, rather than returning one number.

This router is the intended seam for a future AI layer: a model would
receive the same structured evidence these handlers already compute
and turn it into more natural prose, but it would not replace the
underlying analysis.
"""

import re
from datetime import timedelta

from src.comparisons import compare_week_over_week, week_over_week_range
from src.metrics import aggregate
from src.pacing import compute_pacing
from src.search_term_intelligence import negative_keyword_candidates
from src.change_intelligence import describe_changes
from src.competitive import auction_trend
from src.executive_brief import generate_brief
from src.rolling import rolling_8_day_dates, generate_8day_brief, format_date_range
from src.evidence import investigate_with_evidence
from src.investigation import MATERIAL_ACCOUNT_CHANGE
from src.formatting import metric_label
from src.recommendations import generate_recommendations, CATEGORY_HIGH_PRIORITY, CATEGORY_OPPORTUNITY

INTENTS = [
    ("why_change", re.compile(r"\bwhy\b.*\b(decreas|drop|fell|declin|increas|rose|rise|went up|went down)", re.I)),
    ("attention", re.compile(r"\bneed(s)?\s+attention\b|\bwhat.?s wrong\b|\bproblem", re.I)),
    ("opportunities", re.compile(r"\bopportunit", re.I)),
    ("competitive", re.compile(r"\bcompetitiv|\bcompetitor|\bimpression share\b", re.I)),
    ("rolling_8_day", re.compile(r"\b8.?day|\beight.?day|\blast 8\b", re.I)),
    ("top_campaign", re.compile(r"\b(most|highest|best|top)\b.*\bconversion", re.I)),
    ("pacing", re.compile(r"\bpac(e|ing)\b|\bbudget\b", re.I)),
    ("recent_changes", re.compile(r"\bchang(e|ed|es)\b.*\b(before|recent|lately|when)\b|\bwhat changed\b", re.I)),
    ("wasted_spend", re.compile(r"\bwast(e|ed|ing)\b|\bnegative keyword", re.I)),
    ("performance_last_week", re.compile(r"\bperform(ed|ance)\b|\bhow did we do\b|\blast week\b", re.I)),
]

METRIC_WORDS = {
    "conversion": "conversions", "conversions": "conversions",
    "spend": "spend", "cost": "spend",
    "click": "clicks", "clicks": "clicks",
    "impression": "impressions", "impressions": "impressions",
    "ctr": "ctr", "click-through": "ctr",
    "cpc": "cpc", "cost per click": "cpc",
    "cpa": "cpa", "cost per acquisition": "cpa",
    "roas": "roas", "return on ad spend": "roas",
}


def _detect_metric(question, default="conversions"):
    q = question.lower()
    for word, metric in METRIC_WORDS.items():
        if word in q:
            return metric
    return default


def _classify(question):
    for intent, pattern in INTENTS:
        if pattern.search(question):
            return intent
    return None


def _evidence_used(report):
    """Which pages/modules actually contributed evidence to this
    conclusion -- only the ones genuinely touched, never a fixed list,
    so the UI can be honest about what was and wasn't checked."""
    modules = ["Performance Intelligence"]
    if report["localize"].get("ranked_contributors") is not None and not report["localize"]["ranked_contributors"].empty:
        modules.append("Campaign Intelligence")
    for hyp in report["hypotheses"].values():
        stq = hyp.get("search_term_quality")
        if stq and stq.get("changed"):
            modules.append("Search Term Intelligence")
        if hyp.get("budget_context") not in (None, "Unknown", "On pace"):
            modules.append("Budget Pacing")
        if any(w in hyp.get("text", "").lower() for w in ("competitor", "auction", "outrank", "rank pressure")):
            modules.append("Competitive Intelligence")
        if hyp.get("correlated_changes"):
            modules.append("Change Intelligence")
    seen = []
    for m in modules:
        if m not in seen:
            seen.append(m)
    return seen


def _not_material_answer(report, metric, current_range, previous_range):
    """A structured (not a bare string) response for the below-threshold
    case, so the UI can render it with the same card-based presentation
    as a material finding -- explicitly stating that nothing material
    was found rather than silently looking like a lesser version of the
    material response. Never manufactures an investigation: there are no
    signals/alternatives/next-step/evidence-used fields here because none
    were computed -- only what was actually verified."""
    v = report["verify"]
    label = metric_label(metric)
    period_now, period_before = format_date_range(*current_range), format_date_range(*previous_range)

    if v["pct_change"] is not None:
        direction_word = "increased" if v["pct_change"] > 0 else "decreased"
        answer_line = (
            f"{label} {direction_word} {abs(v['pct_change']):.1%} during {period_now} versus "
            f"{period_before}, below the {MATERIAL_ACCOUNT_CHANGE:.0%} materiality threshold used for investigation."
        )
    else:
        answer_line = f"{label} is effectively unchanged during {period_now} versus {period_before}."

    return {
        "type": "not_material",
        "answer": answer_line,
        "assessment": "No material change detected",
        "pct_change": v["pct_change"],
        "threshold": MATERIAL_ACCOUNT_CHANGE,
        "monitoring_action": "Continue routine monitoring -- no investigation is currently warranted. "
                              "Revisit if the trend continues or accelerates in the next period.",
    }


def _why_change_answer(question, context):
    """Returns a structured dict (ANSWER / WHAT CHANGED / LIKELY
    CONTRIBUTING SIGNALS / ALTERNATIVE EXPLANATIONS / RECOMMENDED NEXT
    STEP / EVIDENCE USED / CONFIDENCE) when the metric actually changed
    materially -- this is the one question type the evidence
    architecture supports decomposing this way. Returns a different,
    simpler structured dict (see _not_material_answer) when there's
    nothing to investigate -- never a manufactured finding."""
    campaigns_df = context["campaigns"]
    metric = _detect_metric(question)
    current_range, previous_range = week_over_week_range(campaigns_df)[0:2], week_over_week_range(campaigns_df)[2:4]

    report = investigate_with_evidence(
        campaigns_df, context["changes"], context["auction_insights"], context["search_terms"],
        metric, current_range, previous_range,
    )
    if not report["verify"]["changed_materially"]:
        return _not_material_answer(report, metric, current_range, previous_range)

    v = report["verify"]
    label = metric_label(metric)
    period_now, period_before = format_date_range(*current_range), format_date_range(*previous_range)
    answer_line = (
        f"{label} {v['direction']} {abs(v['pct_change']):.1%} during {period_now} "
        f"versus {period_before}." if v["pct_change"] is not None else
        f"{label} {v['direction']} during {period_now} versus {period_before}."
    )

    top_campaigns = list(report["hypotheses"].keys())
    if top_campaigns:
        named = " and ".join(f'"{c}"' for c in top_campaigns[:2])
        what_changed = f"{named} contributed most to the change."
    else:
        what_changed = "No single campaign stood out as the primary contributor."

    signals = [f'{c}: {report["hypotheses"][c]["text"]}' for c in top_campaigns]
    alternatives = report.get("alternative_explanations", [])[1:]  # first one is already the primary signal
    next_step = report.get("suggested_next_test")
    primary_confidence = report["hypotheses"][top_campaigns[0]]["confidence"] if top_campaigns else "Low"

    return {
        "type": "structured",
        "answer": answer_line,
        "what_changed": what_changed,
        "signals": signals,
        "alternatives": alternatives,
        "next_step": next_step,
        "evidence_used": _evidence_used(report),
        "confidence": primary_confidence,
    }


def _attention_answer(context):
    recs = generate_recommendations(
        context["campaigns"], context["keywords"], context["search_terms"],
        context["changes"], context["auction_insights"], context["campaigns"]["date"].max(),
    )
    priority = [r for r in recs if r.category == CATEGORY_HIGH_PRIORITY]
    if not priority:
        return "No high-priority issues detected right now. See Optimization Center for lower-priority items to review."
    lines = ["Campaigns/items needing attention:"]
    for r in priority[:5]:
        lines.append(f"  - {r.title} ({r.entity}) -- {r.reason}")
    return "\n".join(lines)


def _opportunities_answer(context):
    recs = generate_recommendations(
        context["campaigns"], context["keywords"], context["search_terms"],
        context["changes"], context["auction_insights"], context["campaigns"]["date"].max(),
    )
    opportunities = [r for r in recs if r.category == CATEGORY_OPPORTUNITY]
    if not opportunities:
        return "No clear optimization opportunities identified this period. See Optimization Center for the full list."
    lines = ["Best current optimization opportunities:"]
    for r in opportunities[:5]:
        lines.append(f"  - {r.title} ({r.entity}) -- {r.expected_impact}")
    return "\n".join(lines)


def _competitive_answer(context):
    campaigns_df = context["campaigns"]
    auction_df = context["auction_insights"]
    cur_start, cur_end, prev_start, prev_end = week_over_week_range(campaigns_df)
    lines = []
    for campaign in sorted(campaigns_df["campaign"].unique()):
        trend = auction_trend(auction_df, campaign, (cur_start, cur_end), (prev_start, prev_end))
        rank = trend["lost_is_rank"]
        if rank["current"] is not None and rank["previous"] is not None and (rank["current"] - rank["previous"]) >= 0.03:
            lines.append(
                f'  - "{campaign}": Lost IS (Rank) rose from {rank["previous"]:.1%} to {rank["current"]:.1%} '
                f'(top competitor: {trend["top_competitor"]}).'
            )
    if not lines:
        return "No campaign shows a meaningful rise in rank-based competitive pressure this week."
    return "Increasing competitive/rank pressure detected:\n" + "\n".join(lines)


def _rolling_8_day_answer(context):
    campaigns_df = context["campaigns"]
    dates = rolling_8_day_dates(campaigns_df)
    brief = generate_8day_brief(campaigns_df)
    return f"{format_date_range(dates[0], dates[-1])}: {brief['summary']}"


def answer(question, context):
    """`context` is a dict with keys: campaigns, keywords, search_terms,
    changes, auction_insights (the loaded DataFrames). Returns a
    plain-English string."""
    intent = _classify(question)
    campaigns_df = context["campaigns"]

    if intent == "why_change":
        return _why_change_answer(question, context)

    if intent == "attention":
        return _attention_answer(context)

    if intent == "opportunities":
        return _opportunities_answer(context)

    if intent == "competitive":
        return _competitive_answer(context)

    if intent == "rolling_8_day":
        return _rolling_8_day_answer(context)

    if intent == "top_campaign":
        cur_start, cur_end, _, _ = week_over_week_range(campaigns_df)
        recent = campaigns_df[(campaigns_df["date"] >= cur_start) & (campaigns_df["date"] <= cur_end)]
        perf = aggregate(recent, group_by="campaign")
        top = perf.sort_values("conversions", ascending=False).iloc[0]
        return f'"{top["campaign"]}" generated the most conversions in the last 7 days ({int(top["conversions"])}).'

    if intent == "pacing":
        as_of = campaigns_df["date"].max()
        pacing_df = compute_pacing(campaigns_df, as_of, group_by="campaign")
        total = pacing_df[pacing_df["campaign"] == "ACCOUNT TOTAL"].iloc[0]
        lines = [
            f"Account-wide, we're at {total['pacing_pct_to_date']:.0%} of expected spend-to-date "
            f"({total['status']}), projected to end the month at {total['projected_pct_of_budget']:.0%} of budget."
        ]
        off_pace = pacing_df[(pacing_df["campaign"] != "ACCOUNT TOTAL") & (pacing_df["status"] != "On pace")]
        for _, row in off_pace.iterrows():
            lines.append(f"  - \"{row['campaign']}\" is {row['status'].lower()} ({row['pacing_pct_to_date']:.0%}).")
        lines.append("\nSee Budget Pacing for whether under-pacing campaigns are efficient enough to justify more spend.")
        return "\n".join(lines)

    if intent == "recent_changes":
        as_of = campaigns_df["date"].max()
        recent = context["changes"][context["changes"]["date"] >= as_of - timedelta(days=14)]
        if recent.empty:
            return "No account changes were logged in the last 14 days."
        return "Changes in the last 14 days:\n" + "\n".join(f"  - {line}" for line in describe_changes(recent))

    if intent == "wasted_spend":
        as_of = campaigns_df["date"].max()
        candidates = negative_keyword_candidates(
            context["search_terms"], min_spend=25.0, max_conversions=0,
            start_date=as_of - timedelta(days=29), end_date=as_of,
        )
        if candidates.empty:
            return ("No high-spend, zero-conversion search terms were detected in the last 30 days. "
                    "This is a positive signal; continue monitoring query quality.")
        lines = [f'  - "{r["search_term"]}" ({r["campaign"]}): ${r["spend"]:.2f} spent, 0 conversions'
                 for _, r in candidates.iterrows()]
        return "Search terms worth excluding (high spend, zero conversions, last 30 days):\n" + "\n".join(lines)

    if intent == "performance_last_week":
        comparison = compare_week_over_week(campaigns_df, group_by=None)
        row = comparison.iloc[0]
        brief = generate_brief(campaigns_df)
        return (
            f"Last 7 days vs. the prior 7 days: conversions {row['conversions_pct_change']:+.1%}, "
            f"spend {row['spend_pct_change']:+.1%}, ROAS {row['roas_current']:.2f}x "
            f"(was {row['roas_previous']:.2f}x). {brief['summary']}"
        )

    return (
        "I don't have a deterministic answer for that yet. Try asking about performance (last 8 days or "
        "last week), why a metric changed, top campaigns, campaigns needing attention, optimization "
        "opportunities, competitive pressure, budget pacing, recent changes, or wasted spend."
    )
