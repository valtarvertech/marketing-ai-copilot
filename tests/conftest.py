import pytest

from src.data_loader import (
    load_campaigns, load_changes, load_auction_insights,
    load_search_terms, load_keywords, load_scenario_ground_truth,
)


@pytest.fixture(scope="session")
def campaigns_df():
    return load_campaigns()


@pytest.fixture(scope="session")
def changes_df():
    return load_changes()


@pytest.fixture(scope="session")
def auction_df():
    return load_auction_insights()


@pytest.fixture(scope="session")
def search_terms_df():
    return load_search_terms()


@pytest.fixture(scope="session")
def keywords_df():
    return load_keywords()


@pytest.fixture(scope="session")
def scenario_ground_truth_df():
    return load_scenario_ground_truth()
