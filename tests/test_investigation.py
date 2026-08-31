from datetime import date, timedelta

import pytest

from src.investigation import investigate_range

# Maps each injected ground-truth scenario to the metric worth
# investigating and the family of driver(s) we expect the engine to land
# on. Kept loose (a set of acceptable driver ids) since the exact label
# matters less than "did it find the right kind of story".
SCENARIO_METRIC = {
    "A": "cpc",
    "B": "conversion_rate",
    "C": "clicks",
    "D": "conversion_rate",
    "E": "conversion_rate",
}
EXPECTED_DRIVER_FAMILY = {
    "A": {"cpc_pressure"},
    "B": {"conversion_rate_decline"},
    "C": {"volume_decline", "volume_decline_budget_constrained"},
    "D": {"possible_search_term_waste"},
    "E": {"conversion_rate_improvement"},
}


@pytest.mark.parametrize("scenario_id", ["A", "B", "C", "D", "E"])
def test_engine_identifies_correct_driver_for_each_scenario(
    campaigns_df, changes_df, auction_df, scenario_ground_truth_df, scenario_id
):
    scenario = scenario_ground_truth_df[scenario_ground_truth_df["scenario_id"] == scenario_id].iloc[0]
    start = date.fromisoformat(scenario["start_date"])
    end = date.fromisoformat(scenario["end_date"])
    baseline_end = start - timedelta(days=1)
    baseline_start = baseline_end - (end - start)
    metric = SCENARIO_METRIC[scenario_id]

    report = investigate_range(
        campaigns_df, changes_df, auction_df, metric,
        (start, end), (baseline_start, baseline_end), campaign=scenario["campaign"],
    )

    assert report["verify"]["changed_materially"], (
        f"Scenario {scenario_id}: expected a material change in {metric} for {scenario['campaign']}"
    )

    hypothesis = report["hypotheses"][scenario["campaign"]]
    assert hypothesis["driver"] in EXPECTED_DRIVER_FAMILY[scenario_id], (
        f"Scenario {scenario_id}: expected driver in {EXPECTED_DRIVER_FAMILY[scenario_id]}, "
        f"got '{hypothesis['driver']}' -- {hypothesis['text']}"
    )
    assert hypothesis["confidence"] in {"High", "Medium", "Low"}


def test_no_material_change_skips_investigation(campaigns_df, changes_df, auction_df):
    # Comparing a campaign against itself (same range twice) should
    # always show zero change and no investigation.
    latest = campaigns_df["date"].max()
    same_range = (latest - timedelta(days=6), latest)
    report = investigate_range(
        campaigns_df, changes_df, auction_df, "conversions", same_range, same_range, campaign="Brand Search"
    )
    assert not report["verify"]["changed_materially"]


def test_immaterial_change_conclusion_is_polished_prose_not_leftover_conditional_syntax(campaigns_df, changes_df, auction_df):
    # Regression test for a real copy bug: the immaterial-change message
    # used to read "Cpa did not change materially (3.0% if available) --
    # no investigation warranted." -- wrong acronym casing, and "if
    # available" is a leftover-looking conditional artifact even when the
    # value IS available (which it always is in this branch).
    latest = campaigns_df["date"].max()
    same_range = (latest - timedelta(days=6), latest)
    report = investigate_range(campaigns_df, changes_df, auction_df, "cpa", same_range, same_range, campaign="Brand Search")
    conclusion = report["conclusion"]

    assert "if available" not in conclusion.lower()
    assert "Cpa" not in conclusion  # wrong casing; must be "CPA"
    assert "CPA" in conclusion
    assert "materiality threshold" in conclusion.lower()


def test_confidence_is_never_a_fabricated_precise_statistic(campaigns_df, changes_df, auction_df, scenario_ground_truth_df):
    scenario = scenario_ground_truth_df.iloc[0]
    start = date.fromisoformat(scenario["start_date"])
    end = date.fromisoformat(scenario["end_date"])
    baseline_end = start - timedelta(days=1)
    baseline_start = baseline_end - (end - start)
    report = investigate_range(
        campaigns_df, changes_df, auction_df, "cpc", (start, end), (baseline_start, baseline_end),
        campaign=scenario["campaign"],
    )
    for hypothesis in report["hypotheses"].values():
        assert hypothesis["confidence"] in {"High", "Medium", "Low"}
