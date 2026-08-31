from datetime import date

import pandas as pd

from src.keyword_intelligence import classify_keywords, STRONG, EFFICIENT, MONITOR, WASTE_CANDIDATE


def _row(keyword, spend, conversions, conversion_value, clicks=100, impressions=1000, campaign="A", d=date(2026, 1, 1)):
    return {
        "date": d, "campaign": campaign, "keyword": keyword, "match_type": "Phrase",
        "impressions": impressions, "clicks": clicks, "spend": spend,
        "conversions": conversions, "conversion_value": conversion_value,
    }


def test_waste_candidate_requires_high_spend_and_sub_one_roas_not_cpa_alone():
    # High spend, ROAS < 1.0 (losing money) -> Waste Candidate.
    # A second keyword with high CPA but healthy ROAS must NOT be flagged --
    # this is the exact case the product spec calls out explicitly.
    df = pd.DataFrame([
        _row("losing money", spend=500.0, conversions=5, conversion_value=200.0),   # ROAS 0.4x
        _row("high cpa but valuable", spend=500.0, conversions=2, conversion_value=2000.0),  # CPA $250, ROAS 4x
        _row("baseline", spend=50.0, conversions=5, conversion_value=250.0),
    ])
    result = classify_keywords(df)
    losing = result[result["keyword"] == "losing money"].iloc[0]
    valuable = result[result["keyword"] == "high cpa but valuable"].iloc[0]

    assert losing["status"] == WASTE_CANDIDATE
    assert valuable["status"] != WASTE_CANDIDATE, "high CPA alone must not trigger Waste Candidate when ROAS is healthy"


def test_strong_requires_high_volume_and_above_median_roas():
    df = pd.DataFrame([
        _row("top", spend=100.0, conversions=50, conversion_value=1000.0),
        _row("mid", spend=100.0, conversions=10, conversion_value=200.0),
        _row("low", spend=100.0, conversions=2, conversion_value=40.0),
    ])
    result = classify_keywords(df)
    assert result[result["keyword"] == "top"].iloc[0]["status"] == STRONG


def test_zero_conversions_zero_spend_keyword_does_not_crash():
    df = pd.DataFrame([_row("untouched", spend=0.0, conversions=0, conversion_value=0.0, clicks=0, impressions=0)])
    result = classify_keywords(df)
    assert result.iloc[0]["status"] in {STRONG, EFFICIENT, MONITOR, WASTE_CANDIDATE, "Review"}


def test_empty_dataframe_returns_empty():
    df = pd.DataFrame(columns=["date", "campaign", "keyword", "match_type",
                                "impressions", "clicks", "spend", "conversions", "conversion_value"])
    assert classify_keywords(df).empty
