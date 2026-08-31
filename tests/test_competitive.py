from datetime import date

import pandas as pd

from src.competitive import auction_trend, generate_competitive_commentary


def _row(week_start, campaign, impression_share, lost_is_rank, lost_is_budget, outranking_share=0.5, top_competitor="AT&T"):
    return {
        "week_start_date": week_start, "platform": "Google Ads", "campaign": campaign,
        "impression_share": impression_share, "overlap_rate": 0.3, "position_above_rate": 0.4,
        "top_of_page_rate": 0.6, "absolute_top_rate": 0.2, "outranking_share": outranking_share,
        "lost_is_rank": lost_is_rank, "lost_is_budget": lost_is_budget, "top_competitor": top_competitor,
    }


def test_commentary_attributes_rank_pressure_correctly():
    df = pd.DataFrame([
        _row(date(2026, 1, 1), "A", impression_share=0.60, lost_is_rank=0.15, lost_is_budget=0.10),
        _row(date(2026, 1, 8), "A", impression_share=0.50, lost_is_rank=0.25, lost_is_budget=0.11),
    ])
    trend = auction_trend(df, "A", (date(2026, 1, 8), date(2026, 1, 8)), (date(2026, 1, 1), date(2026, 1, 1)))
    commentary = generate_competitive_commentary("A", trend)
    assert "rank pressure" in commentary.lower()
    assert "percentage points" in commentary.lower()
    assert "0.507" not in commentary and "0.0368" not in commentary  # never a raw decimal


def test_commentary_attributes_budget_limitation_correctly():
    df = pd.DataFrame([
        _row(date(2026, 1, 1), "B", impression_share=0.60, lost_is_rank=0.15, lost_is_budget=0.10),
        _row(date(2026, 1, 8), "B", impression_share=0.50, lost_is_rank=0.16, lost_is_budget=0.22),
    ])
    trend = auction_trend(df, "B", (date(2026, 1, 8), date(2026, 1, 8)), (date(2026, 1, 1), date(2026, 1, 1)))
    commentary = generate_competitive_commentary("B", trend)
    assert "increasingly budget-limited" in commentary.lower()
    assert "suggesting increased rank pressure" not in commentary.lower()  # must not claim the wrong driver


def test_commentary_reports_no_meaningful_change_when_stable():
    df = pd.DataFrame([
        _row(date(2026, 1, 1), "C", impression_share=0.55, lost_is_rank=0.15, lost_is_budget=0.10),
        _row(date(2026, 1, 8), "C", impression_share=0.551, lost_is_rank=0.151, lost_is_budget=0.101),
    ])
    trend = auction_trend(df, "C", (date(2026, 1, 8), date(2026, 1, 8)), (date(2026, 1, 1), date(2026, 1, 1)))
    commentary = generate_competitive_commentary("C", trend)
    assert "no meaningful change" in commentary.lower()


def test_commentary_handles_missing_data_without_crashing():
    df = pd.DataFrame(columns=["week_start_date", "platform", "campaign", "impression_share",
                                "overlap_rate", "position_above_rate", "top_of_page_rate",
                                "absolute_top_rate", "outranking_share", "lost_is_rank",
                                "lost_is_budget", "top_competitor"])
    trend = auction_trend(df, "NoData", (date(2026, 1, 8), date(2026, 1, 8)), (date(2026, 1, 1), date(2026, 1, 1)))
    commentary = generate_competitive_commentary("NoData", trend)
    assert "not enough" in commentary.lower()
