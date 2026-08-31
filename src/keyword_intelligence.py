"""
Keyword-level analysis: same deterministic metric math as campaigns,
just grouped by keyword instead of campaign.
"""

from src.metrics import aggregate


def keyword_performance(keywords_df, start_date=None, end_date=None):
    df = keywords_df
    if start_date is not None:
        df = df[df["date"] >= start_date]
    if end_date is not None:
        df = df[df["date"] <= end_date]
    return aggregate(df, group_by=["campaign", "keyword"])


def top_performers(keywords_df, metric="conversions", top_n=5, start_date=None, end_date=None):
    perf = keyword_performance(keywords_df, start_date, end_date)
    return perf.sort_values(metric, ascending=False).head(top_n)


def high_spend_low_conversion(keywords_df, spend_percentile=0.75, max_conversions=1,
                               start_date=None, end_date=None):
    """Flag keywords spending a lot of money for very few conversions --
    candidates for a bid or match-type review."""
    perf = keyword_performance(keywords_df, start_date, end_date)
    if perf.empty:
        return perf
    spend_threshold = perf["spend"].quantile(spend_percentile)
    return perf[(perf["spend"] >= spend_threshold) & (perf["conversions"] <= max_conversions)].sort_values(
        "spend", ascending=False
    )


STRONG = "Strong"
EFFICIENT = "Efficient"
MONITOR = "Monitor"
REVIEW = "Review"
WASTE_CANDIDATE = "Waste Candidate"


def classify_keywords(keywords_df, start_date=None, end_date=None):
    """Status label per keyword using multiple signals -- volume, ROAS,
    and spend relative to the rest of the set -- rather than CPA alone.
    A high-CPA keyword that still returns strong conversion value is not
    "waste"; only high spend combined with a sub-1.0 ROAS (losing money
    on ad spend) earns that label."""
    perf = keyword_performance(keywords_df, start_date, end_date)
    if perf.empty:
        return perf
    perf = perf.copy()

    median_roas = perf["roas"].median()
    spend_p75 = perf["spend"].quantile(0.75)
    conversions_p75 = perf["conversions"].quantile(0.75)

    def classify(row):
        if row["spend"] >= spend_p75 and row["roas"] < 1.0:
            return WASTE_CANDIDATE
        if row["conversions"] >= conversions_p75 and row["roas"] >= median_roas:
            return STRONG
        if row["roas"] >= median_roas:
            return EFFICIENT
        if row["spend"] >= spend_p75 and row["roas"] < median_roas:
            return REVIEW
        return MONITOR

    perf["status"] = perf.apply(classify, axis=1)
    return perf
