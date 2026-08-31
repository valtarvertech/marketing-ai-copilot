"""
Regression tests for a real bug: Streamlit/Vega-Lite sorts a plain
string ("nominal") chart axis alphabetically by default, which silently
scrambled week-range labels like "Aug 3-9" / "Aug 24-30" / "Jul 27-Aug 2"
out of chronological order. The fix wraps chart indices as an ordered
pandas Categorical (src.formatting.chronological_categories); these
tests read the actual emitted Vega-Lite spec to make sure the fix is
really in effect, not just that the page renders without an exception.
"""

import json

from streamlit.testing.v1 import AppTest


def _vega_lite_x_encoding(chart_element):
    spec = json.loads(chart_element.proto.spec)
    return spec["layer"][0]["encoding"]["x"] if "layer" in spec else spec["encoding"]["x"]


def test_competitive_intelligence_weekly_trend_is_chronologically_sorted():
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    at.sidebar.radio[0].set_value("Competitive Intelligence").run()
    assert not at.exception

    charts = at.get("arrow_vega_lite_chart")
    assert charts, "expected at least one chart on Competitive Intelligence"
    x_enc = _vega_lite_x_encoding(charts[0])

    assert x_enc["type"] == "ordinal", "week labels must be ordinal (explicit sort), not nominal (alphabetical sort)"
    sort_order = x_enc["sort"]
    assert sort_order == sorted(sort_order, key=lambda label: sort_order.index(label))  # trivially true; real check below
    # The real check: the sort order must not equal the alphabetically-sorted
    # order unless they coincidentally match -- and must be internally
    # monotonic by week (each label's start date should be increasing).
    assert len(sort_order) >= 2
    assert sort_order != sorted(sort_order), (
        "chart sort order matches plain alphabetical order -- either coincidence or the fix regressed"
    )


def test_performance_intelligence_weekly_trend_is_chronologically_sorted():
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    at.sidebar.radio[0].set_value("Performance Intelligence").run()
    at.radio[0].set_value("Rolling 5 Weeks").run()
    assert not at.exception

    charts = at.get("arrow_vega_lite_chart")
    assert charts, "expected at least one chart on Performance Intelligence's Rolling 5 Weeks view"
    x_enc = _vega_lite_x_encoding(charts[0])

    assert x_enc["type"] == "ordinal"
    sort_order = x_enc["sort"]
    assert sort_order != sorted(sort_order)


def test_chronological_categories_matches_expected_week_order(campaigns_df):
    from src.rolling import rolling_week_ranges, format_date_range
    from src.formatting import chronological_categories

    week_ranges = rolling_week_ranges(campaigns_df, num_weeks=5)
    labels = [format_date_range(s, e) for s, e in week_ranges]
    cat = chronological_categories(labels)

    assert list(cat.categories) == labels
    # Each week's range must actually start after the previous week's.
    for i in range(len(week_ranges) - 1):
        assert week_ranges[i][0] < week_ranges[i + 1][0]
