from datetime import date, timedelta

import pandas as pd

from src.evidence import (
    campaign_pacing_context, account_benchmark, build_pacing_contexts, investigate_with_evidence,
    CONTEXT_OPPORTUNITY, CONTEXT_CAUTION, CONTEXT_REVIEW, CONTEXT_AT_RISK, CONTEXT_MONITOR, CONTEXT_ON_TRACK,
)
from src.pacing import STATUS_UNDER, STATUS_OVER, STATUS_ON_TRACK


# ---------------------------------------------------------------------------
# The 2x3 pacing-context matrix -- this is the "under-pacing does not
# automatically mean spend more" logic the product spec calls out
# explicitly as the most important pacing behavior to get right.
# ---------------------------------------------------------------------------
def test_under_pacing_with_strong_relative_roas_is_opportunity():
    context, commentary = campaign_pacing_context(STATUS_UNDER, campaign_roas=10.0, account_roas=5.0)
    assert context == CONTEXT_OPPORTUNITY
    assert "spend" not in commentary.lower().split("candidate")[0]  # doesn't bluntly say "spend more"


def test_under_pacing_with_weak_relative_roas_is_caution_not_spend_more():
    context, commentary = campaign_pacing_context(STATUS_UNDER, campaign_roas=2.0, account_roas=5.0)
    assert context == CONTEXT_CAUTION
    assert "not automatically appropriate" in commentary.lower()


def test_over_pacing_with_strong_relative_roas_is_review_not_cut():
    context, commentary = campaign_pacing_context(STATUS_OVER, campaign_roas=8.0, account_roas=5.0)
    assert context == CONTEXT_REVIEW


def test_over_pacing_with_weak_relative_roas_is_at_risk():
    context, commentary = campaign_pacing_context(STATUS_OVER, campaign_roas=2.0, account_roas=5.0)
    assert context == CONTEXT_AT_RISK
    assert "high-priority" in commentary.lower()


def test_on_pace_with_weak_relative_roas_is_monitor_not_at_risk():
    context, _ = campaign_pacing_context(STATUS_ON_TRACK, campaign_roas=2.0, account_roas=5.0)
    assert context == CONTEXT_MONITOR


def test_on_pace_with_strong_relative_roas_is_on_track():
    context, _ = campaign_pacing_context(STATUS_ON_TRACK, campaign_roas=8.0, account_roas=5.0)
    assert context == CONTEXT_ON_TRACK


# ---------------------------------------------------------------------------
# Account benchmark
# ---------------------------------------------------------------------------
def test_account_benchmark_handles_empty_window_without_crashing():
    campaigns = pd.DataFrame([{
        "date": date(2026, 1, 1), "campaign": "A", "impressions": 100, "clicks": 10,
        "spend": 10.0, "conversions": 1, "conversion_value": 50.0,
    }])
    bench = account_benchmark(campaigns, date(2026, 6, 1), date(2026, 6, 30))
    assert bench["roas"] == 0.0  # empty window -> zeros, not a crash


def test_build_pacing_contexts_runs_on_real_data(campaigns_df):
    pacing_df, contexts = build_pacing_contexts(campaigns_df, campaigns_df["date"].max())
    assert set(contexts.keys()) == set(campaigns_df["campaign"].unique())
    for ctx in contexts.values():
        assert ctx["context"] in {
            CONTEXT_OPPORTUNITY, CONTEXT_CAUTION, CONTEXT_REVIEW, CONTEXT_AT_RISK, CONTEXT_MONITOR, CONTEXT_ON_TRACK,
        }


# ---------------------------------------------------------------------------
# Cross-module evidence synthesis
# ---------------------------------------------------------------------------
def test_investigate_with_evidence_adds_search_term_and_budget_context(campaigns_df, changes_df, auction_df, search_terms_df):
    from src.rolling import rolling_week_ranges
    weeks = rolling_week_ranges(campaigns_df, num_weeks=2)
    report = investigate_with_evidence(
        campaigns_df, changes_df, auction_df, search_terms_df, "clicks", weeks[1], weeks[0], campaign="SD-WAN",
    )
    if report["verify"]["changed_materially"]:
        hyp = report["hypotheses"]["SD-WAN"]
        assert "search_term_quality" in hyp
        assert "budget_context" in hyp
        assert report["suggested_next_test"] is not None


def test_investigate_with_evidence_skips_evidence_when_nothing_material(campaigns_df, changes_df, auction_df, search_terms_df):
    latest = campaigns_df["date"].max()
    same_range = (latest - timedelta(days=6), latest)
    report = investigate_with_evidence(
        campaigns_df, changes_df, auction_df, search_terms_df, "conversions", same_range, same_range, campaign="Brand Search",
    )
    assert not report["verify"]["changed_materially"]
    assert report["alternative_explanations"] == []
    assert report["suggested_next_test"] is None
