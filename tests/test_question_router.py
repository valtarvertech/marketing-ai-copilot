from datetime import date

import pytest

from src.question_router import answer, _classify, _detect_metric, _why_change_answer


@pytest.fixture
def context(campaigns_df, keywords_df, search_terms_df, changes_df, auction_df):
    return {
        "campaigns": campaigns_df, "keywords": keywords_df, "search_terms": search_terms_df,
        "changes": changes_df, "auction_insights": auction_df,
    }


@pytest.mark.parametrize("question,expected_intent", [
    ("Why did conversions decrease?", "why_change"),
    ("Why did CPA increase?", "why_change"),
    ("Which campaigns need attention?", "attention"),
    ("Where are the best optimization opportunities?", "opportunities"),
    ("Is competitive pressure increasing?", "competitive"),
    ("How did we perform during the last 8 days?", "rolling_8_day"),
    ("Which campaign generated the most conversions?", "top_campaign"),
    ("Are we pacing to budget?", "pacing"),
    ("What changed recently?", "recent_changes"),
    ("What search terms are wasting spend?", "wasted_spend"),
    ("How did we perform last week?", "performance_last_week"),
])
def test_question_classification(question, expected_intent):
    assert _classify(question) == expected_intent


def test_unrecognized_question_returns_helpful_fallback(context):
    result = answer("What's the meaning of life?", context)
    assert "don't have a deterministic answer" in result.lower()


@pytest.mark.parametrize("question,metric", [
    ("Why did CPA increase?", "cpa"),
    ("Why did clicks drop?", "clicks"),
    ("Why did ROAS decrease?", "roas"),
])
def test_metric_detection_in_why_change_questions(question, metric):
    assert _detect_metric(question) == metric


def test_every_documented_example_question_answers_without_crashing(context):
    # answer() returns either a plain string (most intents) or a
    # structured dict (why_change, when the metric moved materially) --
    # both are valid, a crash or an empty result are not.
    from src.ui_sections import _EXAMPLE_QUESTIONS
    for question in _EXAMPLE_QUESTIONS:
        result = answer(question, context)
        if isinstance(result, dict):
            assert result.get("answer")
        else:
            assert isinstance(result, str) and len(result) > 0


def test_why_change_answer_includes_a_suggested_next_step_when_material(context):
    # UCaaS's synthetic scenario keeps CPC/CPA elevated in the most recent
    # window -- if it's material this week, the answer should include a
    # concrete next step, not just a bare number. If it's not material
    # this particular week, the fallback phrasing must still be
    # professional prose, not a leftover-looking conditional artifact.
    result = answer("Why did CPA increase?", context)
    if isinstance(result, dict):
        assert result.get("next_step")
    else:
        assert "no investigation is currently warranted" in result.lower()
        assert "if available" not in result.lower()


def test_why_change_answer_is_structured_when_a_scenario_is_active(context):
    # Force the structured path using a truncated dataset where a known
    # scenario (Business Fiber's conversion-rate decline) is active, so
    # this test doesn't depend on which week happens to be "latest" in
    # the live dataset.
    truncated = {**context, "campaigns": context["campaigns"][context["campaigns"]["date"] <= date(2026, 7, 17)]}
    result = _why_change_answer("Why did conversions decrease?", truncated)

    assert isinstance(result, dict)
    assert result["type"] == "structured"
    for key in ("answer", "what_changed", "signals", "evidence_used", "confidence"):
        assert key in result
    assert result["confidence"] in {"High", "Medium", "Low"}
    assert "Performance Intelligence" in result["evidence_used"]
    assert len(result["signals"]) > 0


def test_live_demo_dataset_shows_a_material_conversion_decline_in_the_latest_week(context):
    # Regression test for the Ask My Account demo scenario: the current
    # synthetic dataset's most recent 7-day window must show a material
    # (>5%) account-level conversion decline out of the box, so "Why did
    # conversions decrease?" demonstrates the full structured path
    # without needing to truncate/fabricate data at query time. If this
    # ever fails, the synthetic data no longer supports the demo.
    result = _why_change_answer("Why did conversions decrease?", context)
    assert isinstance(result, dict) and result["type"] == "structured"
    for key in ("answer", "what_changed", "signals", "alternatives", "next_step", "evidence_used", "confidence"):
        assert key in result
    assert len(result["signals"]) > 0
    assert result["next_step"]


def test_structured_answer_never_shows_wrong_acronym_casing(context):
    # Regression test: metric.replace("_", " ").title() turns "cpa" into
    # "Cpa" -- both the material and non-material answer builders must
    # use the shared metric_label() helper instead.
    result = answer("Why did CPA increase?", context)
    text = result["answer"] if isinstance(result, dict) else result
    assert "Cpa" not in text
    assert "CPA" in text


def test_what_changed_uses_natural_language_not_python_repr(context):
    # Regression test: an earlier version rendered campaign names with
    # Python's repr() (e.g. "'Business Fiber', 'Brand Search'"), which
    # reads like code, not business language.
    result = _why_change_answer("Why did conversions decrease?", context)
    if isinstance(result, dict) and result.get("what_changed"):
        assert "', '" not in result["what_changed"]


def test_not_material_answer_has_all_required_fields(context):
    # "clicks" is a metric that currently moves well under the 5%
    # materiality threshold in the live dataset -- exercises the
    # non-material structured response end to end.
    result = _why_change_answer("Why did clicks drop?", context)
    assert isinstance(result, dict)
    assert result["type"] == "not_material"
    for key in ("answer", "assessment", "pct_change", "threshold", "monitoring_action"):
        assert key in result
    assert result["threshold"] == 0.05
    assert "no investigation is currently warranted" in result["monitoring_action"].lower()
    # Never manufactures investigation fields for a non-material change.
    assert "signals" not in result and "alternatives" not in result and "next_step" not in result
