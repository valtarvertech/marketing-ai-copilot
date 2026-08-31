import math

from src.formatting import (
    fmt_count, fmt_money, fmt_percent, fmt_ratio_x, fmt_points, fmt_or_dash,
    metric_label, chronological_categories,
)


def test_fmt_percent_never_a_raw_decimal():
    assert fmt_percent(0.0368) == "3.7%"
    assert "0.0368" not in fmt_percent(0.0368)


def test_fmt_money_full_precision_never_truncated():
    result = fmt_money(1333624.17)
    assert result == "$1,333,624.17"
    assert "..." not in result


def test_fmt_points_is_percentage_points_not_percent_of_percent():
    # Impression share moving from 55% to 49% is a 6.0 point drop, not "-6.0%"
    assert fmt_points(0.49 - 0.55) == "-6.0 pts"


def test_fmt_ratio_x_suffix():
    assert fmt_ratio_x(6.13) == "6.13x"


def test_fmt_count_thousands_separator():
    assert fmt_count(1420583) == "1,420,583"


def test_missing_value_helpers_handle_none_nan_and_zero():
    for v in (None, float("nan"), math.nan):
        assert fmt_count(v) == "n/a"
        assert fmt_money(v) == "n/a"
        assert fmt_percent(v) == "n/a"
    assert fmt_count(0) == "0"  # zero is a real value, not missing


def test_metric_label_uses_correct_acronym_casing():
    # str.title() alone would produce "Cpa", "Ctr", "Cpc", "Roas" -- wrong.
    assert metric_label("cpa") == "CPA"
    assert metric_label("ctr") == "CTR"
    assert metric_label("cpc") == "CPC"
    assert metric_label("roas") == "ROAS"
    assert metric_label("conversion_rate") == "Conversion Rate"


def test_fmt_or_dash_handles_none_nan_and_empty_string():
    assert fmt_or_dash(None) == "— (Not set)"
    assert fmt_or_dash(float("nan")) == "— (Not set)"
    assert fmt_or_dash("") == "— (Not set)"
    assert fmt_or_dash("   ") == "— (Not set)"
    assert fmt_or_dash("real value") == "real value"


def test_fmt_or_dash_custom_empty_meaning():
    assert fmt_or_dash(None, empty_meaning="No previous value") == "— (No previous value)"


def test_chronological_categories_preserves_given_order_not_alphabetical():
    labels = ["Jul 27–Aug 2", "Aug 3–9", "Aug 10–16", "Aug 17–23", "Aug 24–30"]
    cat = chronological_categories(labels)
    # Alphabetically, "Aug 10-16" < "Aug 17-23" < "Aug 24-30" < "Aug 3-9" < "Jul 27-Aug 2"
    # -- if categories() didn't preserve insertion order, this would fail.
    assert list(cat.categories) == labels
    assert cat.ordered is True
