from src.recommendations import (
    generate_recommendations, seed_tracked_recommendation_example,
    CATEGORY_HIGH_PRIORITY, CATEGORY_OPPORTUNITY, CATEGORY_INVESTIGATE, CATEGORY_MONITOR, CATEGORY_ORDER,
)


def test_generate_recommendations_runs_on_real_data_without_crashing(campaigns_df, keywords_df, search_terms_df, changes_df, auction_df):
    as_of = campaigns_df["date"].max()
    recs = generate_recommendations(campaigns_df, keywords_df, search_terms_df, changes_df, auction_df, as_of)
    assert len(recs) > 0
    for r in recs:
        assert r.category in CATEGORY_ORDER
        assert r.confidence in {"High", "Medium", "Low"}
        assert r.title and r.entity and r.reason and r.evidence and r.suggested_action


def test_recommendations_are_ordered_by_category_severity(campaigns_df, keywords_df, search_terms_df, changes_df, auction_df):
    as_of = campaigns_df["date"].max()
    recs = generate_recommendations(campaigns_df, keywords_df, search_terms_df, changes_df, auction_df, as_of)
    seen_order = [CATEGORY_ORDER.index(r.category) for r in recs]
    assert seen_order == sorted(seen_order)


def test_high_priority_negative_keywords_are_generated_for_known_waste(campaigns_df, keywords_df, search_terms_df, changes_df, auction_df):
    # Managed Security's synthetic scenario D injects zero-conversion search
    # terms -- this must surface as a High Priority recommendation.
    as_of = campaigns_df["date"].max()
    recs = generate_recommendations(campaigns_df, keywords_df, search_terms_df, changes_df, auction_df, as_of)
    high_priority_entities = [r.entity for r in recs if r.category == CATEGORY_HIGH_PRIORITY]
    assert any("Managed Security" in e for e in high_priority_entities)


def test_pacing_recommendations_never_say_spend_more_for_weak_efficiency(campaigns_df, keywords_df, search_terms_df, changes_df, auction_df):
    as_of = campaigns_df["date"].max()
    recs = generate_recommendations(campaigns_df, keywords_df, search_terms_df, changes_df, auction_df, as_of)
    investigate_recs = [r for r in recs if r.category == CATEGORY_INVESTIGATE and "adjusting budget" in r.title.lower()]
    for r in investigate_recs:
        assert "spend more" not in r.suggested_action.lower()
        assert "before" in r.suggested_action.lower() or "investigate" in r.suggested_action.lower()


def test_seed_tracked_recommendation_example_has_measured_outcome(campaigns_df, changes_df):
    rec = seed_tracked_recommendation_example(campaigns_df, changes_df)
    assert rec is not None
    assert rec.status == "Implemented"
    assert rec.measured_outcome is not None and "%" in rec.measured_outcome
