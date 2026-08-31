from datetime import date

import pandas as pd

from src.search_term_intelligence import (
    classify_search_terms, negative_keyword_candidates, expansion_candidates, waste_share,
    NEGATIVE_CANDIDATE, EXPANSION_CANDIDATE, NEEDS_REVIEW, RELEVANT,
)


def _row(term, spend, conversions, clicks=20, impressions=500, conversion_value=None, campaign="A", d=date(2026, 1, 1)):
    return {
        "date": d, "campaign": campaign, "search_term": term, "matched_keyword": "kw",
        "impressions": impressions, "clicks": clicks, "spend": spend, "conversions": conversions,
        "conversion_value": conversion_value if conversion_value is not None else conversions * 100.0,
    }


def test_classify_negative_candidate_requires_spend_and_zero_conversions():
    df = pd.DataFrame([_row("free stuff", spend=50.0, conversions=0)])
    result = classify_search_terms(df, min_spend=25.0)
    assert result.iloc[0]["classification"] == NEGATIVE_CANDIDATE


def test_classify_expansion_candidate_requires_volume_and_rate():
    df = pd.DataFrame([_row("great product", spend=50.0, conversions=5, clicks=50)])
    result = classify_search_terms(df, min_conversions=3, min_conversion_rate=0.05)
    assert result.iloc[0]["classification"] == EXPANSION_CANDIDATE


def test_classify_relevant_when_nothing_stands_out():
    # Low spend (well under the waste bar) and a low, unremarkable
    # conversion rate (well under the expansion bar) -- nothing to flag.
    df = pd.DataFrame([_row("normal term", spend=10.0, conversions=1, clicks=50)])
    result = classify_search_terms(df, min_spend=25.0, min_conversions=3, min_conversion_rate=0.05)
    assert result.iloc[0]["classification"] == RELEVANT


def test_classify_needs_review_for_borderline_waste_not_yet_crossing_threshold():
    # Spend is 60% of the negative-candidate bar with 1 conversion (not 0) --
    # not a confident "negative candidate" verdict, but not clean either.
    df = pd.DataFrame([_row("maybe waste", spend=16.0, conversions=1, clicks=15, conversion_value=5.0)])
    result = classify_search_terms(df, min_spend=25.0)
    assert result.iloc[0]["classification"] == NEEDS_REVIEW


def test_zero_spend_zero_conversions_does_not_crash_and_is_not_negative():
    df = pd.DataFrame([_row("zero everything", spend=0.0, conversions=0, clicks=0, impressions=0, conversion_value=0.0)])
    result = classify_search_terms(df, min_spend=25.0)
    assert result.iloc[0]["classification"] == RELEVANT  # zero spend can't be "wasted spend"


def test_empty_dataframe_returns_empty_without_crashing():
    df = pd.DataFrame(columns=["date", "campaign", "search_term", "matched_keyword",
                                "impressions", "clicks", "spend", "conversions", "conversion_value"])
    assert classify_search_terms(df).empty
    assert negative_keyword_candidates(df).empty
    assert expansion_candidates(df).empty


def test_waste_share_computes_correctly_and_handles_zero_total_spend():
    df = pd.DataFrame([
        _row("waste one", spend=30.0, conversions=0, campaign="A"),
        _row("good one", spend=70.0, conversions=5, clicks=50, campaign="A"),
    ])
    result = waste_share(df, "A", date(2026, 1, 1), date(2026, 1, 1), min_spend=25.0)
    assert result["total_spend"] == 100.0
    assert result["wasted_spend"] == 30.0
    assert round(result["wasted_share"], 2) == 0.3

    empty_df = pd.DataFrame(columns=df.columns)
    empty_result = waste_share(empty_df, "A", date(2026, 1, 1), date(2026, 1, 1))
    assert empty_result["wasted_share"] == 0.0  # no division by zero
