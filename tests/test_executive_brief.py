from datetime import date

from src.executive_brief import generate_brief


def test_brief_detects_known_conversion_rate_decline_scenario(campaigns_df):
    # Scenario B (Business Fiber conversion-rate decline) is active in
    # mid-July; as of 2026-07-17 the trailing 7 days should read unfavorable.
    truncated = campaigns_df[campaigns_df["date"] <= date(2026, 7, 17)]
    brief = generate_brief(truncated)
    assert brief["overall"] == "Unfavorable"
    assert brief["worst_metric"] == "conversion_rate"
    assert "Business Fiber" in brief["investigate_campaigns"]


def test_brief_detects_known_cpc_pressure_scenario_as_cpa_issue(campaigns_df):
    # Scenario A (Enterprise Voice CPC pressure) pushes CPA up mid-August.
    truncated = campaigns_df[campaigns_df["date"] <= date(2026, 8, 13)]
    brief = generate_brief(truncated)
    assert brief["overall"] == "Unfavorable"
    assert brief["worst_metric"] == "cpa"


def test_brief_reports_stable_when_nothing_material_changed(campaigns_df):
    # A short, quiet window early in the dataset before any scenario starts.
    truncated = campaigns_df[campaigns_df["date"] <= date(2026, 6, 20)]
    brief = generate_brief(truncated)
    assert brief["overall"] == "Stable"
    assert brief["investigate_campaigns"] == []


def test_brief_summary_is_short(campaigns_df):
    brief = generate_brief(campaigns_df)
    # "2-4 sentences" -- a rough proxy is keeping it well under a paragraph.
    assert len(brief["summary"]) < 500
