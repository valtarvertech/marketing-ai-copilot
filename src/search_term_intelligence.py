"""
Search-term analysis: surfaces wasted spend (high spend, zero
conversions) and possible expansion opportunities (search terms
converting well that aren't yet dedicated keywords).

This module only ever produces recommendations for a human to review --
it never modifies a campaign automatically.
"""

from src.metrics import aggregate


def search_term_performance(search_terms_df, start_date=None, end_date=None):
    df = search_terms_df
    if start_date is not None:
        df = df[df["date"] >= start_date]
    if end_date is not None:
        df = df[df["date"] <= end_date]
    return aggregate(df, group_by=["campaign", "search_term"])


def negative_keyword_candidates(search_terms_df, min_spend=25.0, max_conversions=0,
                                 start_date=None, end_date=None):
    """Search terms that have spent at least min_spend with
    max_conversions or fewer conversions -- likely wasted spend."""
    perf = search_term_performance(search_terms_df, start_date, end_date)
    if perf.empty:
        return perf
    return perf[(perf["spend"] >= min_spend) & (perf["conversions"] <= max_conversions)].sort_values(
        "spend", ascending=False
    )


def expansion_candidates(search_terms_df, min_conversions=3, min_conversion_rate=0.05,
                          start_date=None, end_date=None):
    """Search terms already converting well -- worth adding as a
    dedicated keyword to gain more control over bids/match type."""
    perf = search_term_performance(search_terms_df, start_date, end_date)
    if perf.empty:
        return perf
    return perf[
        (perf["conversions"] >= min_conversions) & (perf["conversion_rate"] >= min_conversion_rate)
    ].sort_values("conversions", ascending=False)


NEGATIVE_CANDIDATE = "Negative Candidate"
EXPANSION_CANDIDATE = "Expansion Candidate"
NEEDS_REVIEW = "Needs Review"
RELEVANT = "Relevant"


def classify_search_terms(search_terms_df, min_spend=25.0, min_conversions=3, min_conversion_rate=0.05,
                           start_date=None, end_date=None):
    """Deterministic, multi-signal classification for every search term in
    the period -- not just the ones crossing a single hard threshold.
    Requires reasonable evidence in either direction before calling
    something a Negative or Expansion candidate; anything ambiguous is
    Needs Review rather than silently defaulting to "fine"."""
    perf = search_term_performance(search_terms_df, start_date, end_date)
    if perf.empty:
        return perf

    def classify(row):
        if row["spend"] >= min_spend and row["conversions"] == 0:
            return NEGATIVE_CANDIDATE
        if row["conversions"] >= min_conversions and row["conversion_rate"] >= min_conversion_rate:
            return EXPANSION_CANDIDATE
        # Borderline waste: meaningful spend, essentially no return, but not
        # quite over the "zero conversions" bar -- worth a look, not a verdict.
        borderline_waste = row["spend"] >= min_spend * 0.6 and row["conversions"] <= 1 and row["roas"] < 1.0
        # Borderline expansion: converting, but not quite at the volume/rate
        # bar for a confident recommendation.
        borderline_expansion = 0 < row["conversions"] < min_conversions and row["conversion_rate"] >= min_conversion_rate
        if borderline_waste or borderline_expansion:
            return NEEDS_REVIEW
        return RELEVANT

    perf = perf.copy()
    perf["classification"] = perf.apply(classify, axis=1)
    return perf


def waste_share(search_terms_df, campaign, start_date, end_date, min_spend=25.0):
    """Summarize how much of a campaign's search-term spend in a period
    looks wasted (Negative Candidate terms) -- used to check whether
    search-term quality is a plausible contributor to a performance
    shift (src/evidence.py)."""
    subset = search_terms_df[search_terms_df["campaign"] == campaign]
    classified = classify_search_terms(subset, min_spend=min_spend, start_date=start_date, end_date=end_date)
    if classified.empty:
        return {"total_spend": 0.0, "wasted_spend": 0.0, "wasted_share": 0.0, "wasted_terms": 0}

    total_spend = classified["spend"].sum()
    wasted = classified[classified["classification"] == NEGATIVE_CANDIDATE]
    wasted_spend = wasted["spend"].sum()
    return {
        "total_spend": total_spend,
        "wasted_spend": wasted_spend,
        "wasted_share": (wasted_spend / total_spend) if total_spend else 0.0,
        "wasted_terms": len(wasted),
    }
