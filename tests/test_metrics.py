import pandas as pd

from src.metrics import safe_div, add_derived_metrics, aggregate, favorability


def test_safe_div_scalar_handles_zero_denominator():
    assert safe_div(10, 0) == 0.0
    assert safe_div(10, 0, default=-1) == -1
    assert safe_div(10, 5) == 2.0


def test_safe_div_series_handles_zero_denominator():
    numerator = pd.Series([10, 20, 30])
    denominator = pd.Series([5, 0, 10])
    result = safe_div(numerator, denominator)
    assert result.tolist() == [2.0, 0.0, 3.0]


def test_add_derived_metrics_known_values():
    df = pd.DataFrame([{
        "impressions": 1000, "clicks": 100, "spend": 200.0,
        "conversions": 10, "conversion_value": 500.0,
    }])
    result = add_derived_metrics(df).iloc[0]
    assert result["ctr"] == 0.1
    assert result["cpc"] == 2.0
    assert result["conversion_rate"] == 0.1
    assert result["cpa"] == 20.0
    assert result["roas"] == 2.5


def test_add_derived_metrics_zero_clicks_does_not_crash():
    df = pd.DataFrame([{
        "impressions": 500, "clicks": 0, "spend": 0.0,
        "conversions": 0, "conversion_value": 0.0,
    }])
    result = add_derived_metrics(df).iloc[0]
    assert result["ctr"] == 0.0
    assert result["cpc"] == 0.0
    assert result["conversion_rate"] == 0.0
    assert result["cpa"] == 0.0
    assert result["roas"] == 0.0


def test_aggregate_sums_before_dividing_not_average_of_ratios():
    # Day 1: tiny volume with a misleadingly high conversion rate.
    # Day 2: huge volume with a normal conversion rate.
    # The correct blended rate weights by volume; a naive average of the
    # two daily rates would be wrong.
    df = pd.DataFrame([
        {"impressions": 100, "clicks": 10, "spend": 10.0, "conversions": 5, "conversion_value": 50.0},   # 50% CVR, tiny volume
        {"impressions": 100000, "clicks": 10000, "spend": 10000.0, "conversions": 500, "conversion_value": 5000.0},  # 5% CVR, huge volume
    ])
    total = aggregate(df, group_by=None).iloc[0]

    naive_average_of_ratios = (0.5 + 0.05) / 2  # what you'd get if you (incorrectly) averaged the two days
    correct_blended_rate = 505 / 10010  # sum conversions / sum clicks

    assert round(total["conversion_rate"], 6) == round(correct_blended_rate, 6)
    assert total["conversion_rate"] != naive_average_of_ratios


def test_favorability_higher_is_better_metrics():
    assert favorability("conversions", 0.10) == "Favorable"
    assert favorability("conversions", -0.10) == "Unfavorable"
    assert favorability("roas", 0.10) == "Favorable"
    assert favorability("conversion_rate", -0.10) == "Unfavorable"


def test_favorability_lower_is_better_metrics_are_not_naively_up_is_good():
    # This is the bug being fixed: a CPA increase must read Unfavorable,
    # not Favorable just because the number went up.
    assert favorability("cpa", 0.10) == "Unfavorable"
    assert favorability("cpa", -0.10) == "Favorable"
    assert favorability("cpc", 0.10) == "Unfavorable"
    assert favorability("cpc", -0.10) == "Favorable"


def test_favorability_neutral_and_flat_and_missing():
    assert favorability("spend", 0.50) == "Neutral"
    assert favorability("conversions", 0.01) == "Flat"
    assert favorability("conversions", float("nan")) == "No data"
    assert favorability("conversions", None) == "No data"


def test_aggregate_group_by_campaign(campaigns_df):
    perf = aggregate(campaigns_df, group_by="campaign")
    assert set(perf["campaign"]) == set(campaigns_df["campaign"].unique())
    # Every row should have non-negative metrics and no crashes from
    # zero-division anywhere in 90 days x 7 campaigns of real data.
    assert (perf["ctr"] >= 0).all()
    assert (perf["roas"] >= 0).all()
