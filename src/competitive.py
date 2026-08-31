"""
Competitive / auction intelligence.

Works from synthetic weekly auction-insight rows (impression share,
outranking share, lost impression share due to rank vs. due to budget).
This is the evidence source that lets the investigation engine tell
apart two very different stories that can look similar in raw
performance data:

  - CPC rising because a competitor is outranking you (rank problem)
  - Volume falling because you're capped by your own budget (budget problem)

We only ever describe what the auction data shows -- we do not claim a
competitor's specific action caused a performance change unless the
direction and timing of the auction metrics support it.
"""


def auction_trend(auction_df, campaign, current_range, previous_range):
    """Compare a campaign's auction metrics between two week-aligned
    periods. Ranges are (start_date, end_date) tuples; auction rows are
    matched by falling within the range (weekly rows, so this naturally
    picks up whichever weeks overlap)."""
    subset = auction_df[auction_df["campaign"] == campaign]

    current = subset[
        (subset["week_start_date"] >= current_range[0]) & (subset["week_start_date"] <= current_range[1])
    ]
    previous = subset[
        (subset["week_start_date"] >= previous_range[0]) & (subset["week_start_date"] <= previous_range[1])
    ]

    metrics = ["impression_share", "outranking_share", "lost_is_rank", "lost_is_budget"]
    result = {}
    for metric in metrics:
        cur_val = current[metric].mean() if not current.empty else None
        prev_val = previous[metric].mean() if not previous.empty else None
        result[metric] = {"current": cur_val, "previous": prev_val}

    top_competitor = subset["top_competitor"].iloc[-1] if not subset.empty else None
    result["top_competitor"] = top_competitor
    return result


def summarize_competitive_pressure(trend):
    """Turn an auction_trend() result into plain-English evidence lines."""
    lines = []
    rank = trend["lost_is_rank"]
    budget = trend["lost_is_budget"]
    outranking = trend["outranking_share"]
    impression_share = trend["impression_share"]

    if rank["current"] is not None and rank["previous"] is not None:
        rank_delta = rank["current"] - rank["previous"]
        if rank_delta > 0.03:
            lines.append(
                f"Lost impression share due to rank rose from {rank['previous']:.1%} to {rank['current']:.1%}, "
                f"consistent with a competitor (most recently {trend['top_competitor']}) outranking this campaign more often."
            )

    if budget["current"] is not None and budget["previous"] is not None:
        budget_delta = budget["current"] - budget["previous"]
        if budget_delta > 0.03:
            lines.append(
                f"Lost impression share due to budget rose from {budget['previous']:.1%} to {budget['current']:.1%}, "
                f"suggesting the campaign is being held back by its budget rather than by competition or ad rank."
            )

    if impression_share["current"] is not None and impression_share["previous"] is not None:
        is_delta = impression_share["current"] - impression_share["previous"]
        if abs(is_delta) > 0.03:
            direction = "fell" if is_delta < 0 else "rose"
            lines.append(f"Overall impression share {direction} from {impression_share['previous']:.1%} to {impression_share['current']:.1%}.")

    if not lines:
        lines.append("No meaningful change in auction/competitive metrics for this period.")
    return lines


def generate_competitive_commentary(campaign, trend, threshold_pts=2.0):
    """One deterministic sentence contrasting rank-driven vs. budget-driven
    visibility loss, in percentage-point terms (never a percent of a
    percent). This is the headline sentence for Competitive Intelligence;
    summarize_competitive_pressure() above remains available for the
    fuller evidence list."""
    impression_share, rank, budget = trend["impression_share"], trend["lost_is_rank"], trend["lost_is_budget"]

    if impression_share["current"] is None or impression_share["previous"] is None:
        return f'Not enough auction data to assess "{campaign}" this period.'

    is_delta_pts = (impression_share["current"] - impression_share["previous"]) * 100
    rank_delta_pts = (
        (rank["current"] - rank["previous"]) * 100 if rank["current"] is not None and rank["previous"] is not None else None
    )
    budget_delta_pts = (
        (budget["current"] - budget["previous"]) * 100
        if budget["current"] is not None and budget["previous"] is not None else None
    )

    if (
        abs(is_delta_pts) < threshold_pts
        and (rank_delta_pts is None or abs(rank_delta_pts) < threshold_pts)
        and (budget_delta_pts is None or abs(budget_delta_pts) < threshold_pts)
    ):
        return f'"{campaign}" shows no meaningful change in competitive/auction metrics this period.'

    direction = "declined" if is_delta_pts < 0 else "increased"
    sentence = f'"{campaign}" impression share {direction} {abs(is_delta_pts):.1f} percentage points'

    if rank_delta_pts is not None and rank_delta_pts >= threshold_pts and (budget_delta_pts is None or rank_delta_pts > budget_delta_pts):
        sentence += (
            f" while Lost IS (Rank) increased {rank_delta_pts:.1f} points, suggesting increased rank "
            f"pressure rather than budget limitation."
        )
    elif budget_delta_pts is not None and budget_delta_pts >= threshold_pts and (rank_delta_pts is None or budget_delta_pts > rank_delta_pts):
        sentence += (
            f" while Lost IS (Budget) increased {budget_delta_pts:.1f} points, suggesting the campaign is "
            f"increasingly budget-limited rather than under rank pressure."
        )
    elif rank_delta_pts is not None and budget_delta_pts is not None and rank_delta_pts >= threshold_pts and budget_delta_pts >= threshold_pts:
        sentence += (
            f", with both Lost IS (Rank) (+{rank_delta_pts:.1f} pts) and Lost IS (Budget) "
            f"(+{budget_delta_pts:.1f} pts) rising -- this period's data doesn't cleanly separate rank "
            f"pressure from budget limitation."
        )
    else:
        sentence += ", though neither Lost IS (Rank) nor Lost IS (Budget) moved enough this period to explain it clearly."

    sentence += " Based on synthetic auction-insight data -- directional, not a precise competitive measurement."
    return sentence
